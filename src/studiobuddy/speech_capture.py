"""Studio Buddy's token-aware, bounded capture backend; independent of PushTalk.

Heavy audio/model imports occur only when explicitly launching this service.
Audio, origin token and watchdog completion share one lock. Transcription and
GUI IPC never hold it. Late results retain their origin through GUI acceptance.
"""

import argparse
import fcntl
import json
import queue
import signal
import socket
import sys
import threading
from dataclasses import dataclass

from studiobuddy.voice_input import register_action, request, runtime_path, voice_state

SAMPLE_RATE = 16000


@dataclass(frozen=True)
class CaptureJob:
    token: str
    chunks: tuple


class CaptureEngine:
    def __init__(self, *, max_samples, submit):
        self.max_samples = max_samples
        self.submit = submit
        self.lock = threading.Lock()
        self.jobs = queue.Queue(maxsize=1)
        self.recording = None
        self.current = None
        self.chunks = []
        self.samples = 0
        self.closed = False

    def start(self, token):
        with self.lock:
            if self.closed:
                raise RuntimeError("Speech backend is shutting down")
            if self.current == token:
                return  # Retries must not erase audio or reopen a completed job.
            self._discard()
            self.current = self.recording = token

    def _discard(self):
        self.recording = None
        self.chunks = []
        self.samples = 0
        try:
            self.jobs.get_nowait()
        except queue.Empty:
            pass

    def _seal(self):
        job = CaptureJob(self.recording, tuple(self.chunks))
        self._discard()
        self.jobs.put_nowait(job)

    def feed(self, samples):
        with self.lock:
            if self.recording is None:
                return
            # Enforce the cap in the callback, even if the control thread hangs.
            chunk = samples[: self.max_samples - self.samples]
            if len(chunk):
                self.chunks.append(chunk)
                self.samples += len(chunk)
            if self.samples >= self.max_samples:
                self._seal()

    def stop(self, token):
        with self.lock:
            if token == self.recording:
                self._seal()

    def cancel(self, token, *, supersede=False):
        with self.lock:
            if token == self.current or supersede:
                self.current = None
                self._discard()

    def process(self, job, transcribe):
        with self.lock:
            if job.token != self.current or self.closed:
                return
        text = transcribe(job.chunks)
        with self.lock:
            current = job.token == self.current and not self.closed
        # Cancellation can race this call: the GUI's durable identity check is
        # the final acceptance boundary, so never relabel with self.current.
        if current and text:
            self.submit(job.token, text)

    def worker(self, transcribe):
        while True:
            job = self.jobs.get()
            if job is None:
                return
            try:
                self.process(job, transcribe)
            except Exception:  # noqa: BLE001 — isolate optional model/transport failures per job
                # Audio, transcripts, remote error bodies and credentials are
                # deliberately absent from backend logs.
                print("Studio Buddy: transcription or delivery failed", file=sys.stderr)

    def close(self):
        with self.lock:
            self.closed = True
            self.current = None
            self._discard()
            self.jobs.put_nowait(None)


def handle(engine, directory, payload):
    if not isinstance(payload, dict):
        raise TypeError("Expected object")
    action = payload.get("action")
    if action == "status":
        with engine.lock:
            return {"ok": True, "recording": engine.recording is not None}
    token = payload.get("token")
    if not isinstance(token, str) or not token or len(token) > 128:
        raise ValueError("A recording token is required")
    if action == "start":
        # Prevent a timed-out/queued request from starting after its GUI or
        # listener has revoked it. This transaction is short; no IPC inside.
        with voice_state(directory) as state:
            if state.get("intent") != token or state.get("recording") != token:
                return {"ok": True}
            engine.start(token)
    elif action == "stop":
        engine.stop(token)
    elif action == "cancel":
        with voice_state(directory) as state:
            # Cancelling the latest intent also discards older audio when a new
            # GUI preparation failed before replacing it. An old worker never
            # gets this authority after a newer generation has been registered.
            latest = state.get("generation") == token and state.get("recording") is None
            engine.cancel(token, supersede=latest)
    else:
        raise ValueError("Unknown capture command")
    return {"ok": True}


def serve(server, engine, directory, shutdown):
    server.settimeout(0.5)
    while not shutdown.is_set():
        try:
            connection, _ = server.accept()
        except TimeoutError:
            continue
        with connection:
            connection.settimeout(2)
            try:
                data = bytearray()
                while b"\n" not in data and len(data) <= 1024:
                    chunk = connection.recv(1024)
                    if not chunk:
                        break
                    data.extend(chunk)
                if len(data) > 1024 or b"\n" not in data:
                    raise ValueError("Invalid capture command")
                result = handle(engine, directory, json.loads(data))
            except (OSError, ValueError, TypeError, RuntimeError):
                result = {"ok": False, "error": "Capture command failed"}
            try:
                connection.sendall(json.dumps(result).encode() + b"\n")
            except OSError:
                pass


def revoke(token=None):
    if token is None:
        token = register_action("cancel")
    try:
        request("cancel", token=token)
    except (OSError, ValueError, TypeError, RuntimeError):
        pass  # Durable revocation works even if the GUI is absent or hung.


def run(args):
    directory = runtime_path()
    # A stable inode protects bind/unlink and the complete model/mic lifetime.
    with (directory / "capture-owner.lock").open("a+") as owner:
        try:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Studio Buddy speech backend is already running") from None
        shutdown = threading.Event()
        previous = {}
        for sig in (signal.SIGTERM, signal.SIGINT):
            previous[sig] = signal.signal(sig, lambda *_: shutdown.set())
        path = directory / "capture.sock"
        engine = CaptureEngine(
            max_samples=int(args.max_duration * SAMPLE_RATE),
            submit=lambda token, text: request("submit", text, token=token),
        )
        stream = None
        try:
            revoke()
            # This optional extra is never imported in the normal UI or tests.
            import numpy as np
            import sounddevice as sd
            from faster_whisper import WhisperModel

            model = WhisperModel(
                args.model, device="cpu", compute_type=args.compute_type, cpu_threads=args.threads
            )

            def transcribe(chunks):
                if not chunks:
                    return ""
                audio = np.concatenate(chunks)
                segments, _ = model.transcribe(
                    audio,
                    language=None if args.language == "auto" else args.language,
                    beam_size=5,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 300},
                    condition_on_previous_text=False,
                )
                return "".join(segment.text for segment in segments).strip()

            if shutdown.is_set():
                return
            stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="float32",
                device=args.audio_device,
                callback=lambda data, *_: engine.feed(data[:, 0].copy()),
            )
            stream.start()
            threading.Thread(target=engine.worker, args=(transcribe,), daemon=True).start()
            with socket.socket(socket.AF_UNIX) as server:
                path.unlink(missing_ok=True)
                server.bind(str(path))
                path.chmod(0o600)  # parent is private before bind
                server.listen(8)
                serve(server, engine, directory, shutdown)
        finally:
            # Discard audio and durably revoke before a slow stream close or
            # GUI IPC; an already-issued submit must fail during shutdown too.
            engine.close()
            token = None
            try:
                try:
                    token = register_action("cancel")
                finally:
                    if stream is not None:
                        stream.close()
            finally:
                try:
                    path.unlink(missing_ok=True)
                    if token is not None:
                        revoke(token)
                finally:
                    for sig, handler in previous.items():
                        signal.signal(sig, handler)


def main():
    parser = argparse.ArgumentParser(description="Studio Buddy token-aware speech backend")
    parser.add_argument("--model", default="small.en")
    parser.add_argument("--compute-type", default="int8")
    parser.add_argument("--threads", type=int, default=4)
    parser.add_argument("--language", default="en")
    parser.add_argument("--max-duration", type=float, default=120)
    parser.add_argument("--audio-device", default=None)
    args = parser.parse_args()
    if not 0 < args.max_duration <= 120 or args.threads < 1:
        parser.error("max-duration must be in (0, 120] and threads must be positive")
    try:
        run(args)
    except (OSError, RuntimeError, ImportError):
        print(
            "Studio Buddy: speech backend failed; check the speech extra and audio device",
            file=sys.stderr,
        )
        return 1
    return 0
