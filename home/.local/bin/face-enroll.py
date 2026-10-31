#!/usr/bin/env python3
"""Face model manager for Howdy: preview + enroll + list/remove. Windows Hello style."""
import os, re, subprocess, sys, threading, time
import gi
gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, GLib, GdkPixbuf, Gdk, Gio, Pango
import cv2

DEV = '/dev/video42'
CASCADE = '/usr/share/opencv4/haarcascades/haarcascade_frontalface_default.xml'
LOG = open('/tmp/face-enroll.log', 'w', buffering=1)

def log(msg):
    LOG.write(f'{time.strftime("%H:%M:%S")}.{int(time.time()*1000)%1000:03d} {msg}\n')

def run_bg(args, on_done):
    def worker():
        p = subprocess.run(args, capture_output=True, text=True, timeout=60)
        GLib.idle_add(on_done, (p.stdout or '') + (p.stderr or ''))
    threading.Thread(target=worker, daemon=True).start()

CSS = b"""
.view-card { background: #000; border-radius: 12px; }
.status-text { font-size: 15px; font-weight: 500; color: @theme_text_color; margin: 4px 0; }
.dim { color: @theme_unfocused_fg_color; font-size: 12px; }
.enroll-row entry { border-radius: 8px; }
.enroll-row button { border-radius: 8px; }
.section-title { font-size: 13px; font-weight: 600; color: @theme_unfocused_fg_color; letter-spacing: 0.5px; }
.model-row { background: @theme_base_color; border-radius: 10px; padding: 6px 10px; margin: 3px 0; }
.model-label { color: @theme_text_color; font-size: 13px; }
.model-date { color: @theme_unfocused_fg_color; font-size: 11px; }
"""

class EnrollWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title='Face Models')
        self.set_default_size(540, 820)
        self.set_resizable(False)

        prov = Gtk.CssProvider()
        prov.load_from_data(CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), prov, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        self.face_cascade = cv2.CascadeClassifier(CASCADE)
        self.face_ok_frames = 0
        self.running = True
        self.lock = threading.Lock()
        self.latest = None
        self.last_frame_time = 0
        self.cap = None
        self.bridge = None
        self.bridge_live = False
        self.enrolling = False
        self._spawn_bridge()

        root = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10,
                       margin_top=14, margin_bottom=14, margin_start=14, margin_end=14)
        self.set_child(root)

        title = Gtk.Label(label='<b>Face Recognition Setup</b>', use_markup=True)
        title.add_css_class('status-text')
        root.append(title)

        frame = Gtk.AspectFrame(ratio=480/640.0)
        frame.add_css_class('view-card')
        self.pic = Gtk.Picture(hexpand=True, vexpand=True)
        frame.set_child(self.pic)
        root.append(frame)

        self.status = Gtk.Label(label='Starting camera…')
        self.status.add_css_class('status-text')
        root.append(self.status)

        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        row.add_css_class('enroll-row')
        self.entry = Gtk.Entry(placeholder_text='Model label (optional)', hexpand=True)
        row.append(self.entry)
        self.btn = Gtk.Button(label='Enroll', sensitive=False)
        self.btn.add_css_class('suggested-action')
        self.btn.connect('clicked', self._enroll)
        row.append(self.btn)
        root.append(row)

        root.append(Gtk.Separator())
        mrow = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        mt = Gtk.Label(label='ENROLLED MODELS', hexpand=True, xalign=0)
        mt.add_css_class('section-title')
        mrow.append(mt)
        rbtn = Gtk.Button(icon_name='view-refresh-symbolic')
        rbtn.add_css_class('flat')
        rbtn.set_tooltip_text('Refresh list')
        rbtn.connect('clicked', lambda *_: self._refresh_list())
        mrow.append(rbtn)
        root.append(mrow)

        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class('boxed-list')
        scroll = Gtk.ScrolledWindow(child=self.listbox, min_content_height=80, max_content_height=150)
        scroll.set_propagate_natural_height(True)
        root.append(scroll)

        self.connect('close-request', self._on_close)
        threading.Thread(target=self._capture_loop, daemon=True).start()
        GLib.timeout_add(100, self._present)
        self._refresh_list()

    def _spawn_bridge(self):
        env = dict(os.environ, IR_BRIDGE_LIFETIME_SEC='28800')
        t0 = time.time()
        self.bridge = subprocess.Popen(['/usr/local/bin/ir_bridge_run.sh'],
                                       env=env,
                                       stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                       text=True)
        def fwd():
            for line in self.bridge.stdout:
                log(f'bridge: {line.rstrip()}')
                if 'LED on' in line or 'started pid' in line:
                    self.bridge_live = True
        self.bridge_live = False
        threading.Thread(target=fwd, daemon=True).start()
        self.last_frame_time = time.time()
        log(f'spawn bridge pid={self.bridge.pid} took {time.time()-t0:.3f}s')

    def _capture_loop(self):
        cap = None
        n_iter = 0
        empty_reads = 0
        while self.running:
            if self.enrolling:
                # howdy add takes the camera — release ours and idle until done
                if cap is not None:
                    cap.release()
                    cap = None
                time.sleep(0.3)
                continue
            if cap is None or not cap.isOpened():
                if not self.bridge_live:
                    time.sleep(0.2)
                    continue
                time.sleep(2.5)
                t0 = time.time()
                self.cap = cap = cv2.VideoCapture(DEV, cv2.CAP_V4L2)
                log(f'cap open {"OK" if cap.isOpened() else "FAIL"} took {time.time()-t0:.3f}s')
                if not cap.isOpened():
                    cap = None
                    time.sleep(1.0)
                    continue

            t0 = time.time()
            ok, f = cap.read()
            read_ms = (time.time() - t0) * 1000
            if not ok or f is None:
                empty_reads += 1
                if empty_reads > 60:
                    # wedge: consumer opened at bad time → loopback never delivers.
                    # full reset: release cap, respawn bridge, reopen cleanly.
                    log(f'wedge: {empty_reads} empty reads — full reset')
                    cap.release(); cap = None
                    empty_reads = 0
                    if self.bridge is not None:
                        self.bridge.terminate()
                    self.bridge_live = False
                    self._spawn_bridge()
                continue
            empty_reads = 0
            mean = f.mean()
            if mean <= 5:
                continue

            t0 = time.time()
            gray = f if len(f.shape) == 2 else cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
            h, w = gray.shape[:2]
            faces = self.face_cascade.detectMultiScale(gray, 1.2, 5, minSize=(80, 80))
            det_ms = (time.time() - t0) * 1000

            cx, cy, r = w // 2, h // 2, min(w, h) // 3
            in_circle = False
            for (x, y, fw, fh) in faces[:1]:
                fcx, fcy = x + fw // 2, y + fh // 2
                in_circle = ((fcx - cx) ** 2 + (fcy - cy) ** 2) ** 0.5 < r * 0.5 and fw > r * 0.4

            self.face_ok_frames = self.face_ok_frames + 1 if in_circle else 0
            ready = self.face_ok_frames >= 5
            color = (0, 230, 120) if in_circle else (70, 160, 255)

            vis = cv2.cvtColor(gray, cv2.COLOR_GRAY2RGB)
            cv2.circle(vis, (cx, cy), r, color, 4, cv2.LINE_AA)
            cv2.circle(vis, (cx, cy), r - 10, (*color[:2], 60), 1, cv2.LINE_AA)
            for (x, y, fw, fh) in faces[:1]:
                cv2.rectangle(vis, (x, y), (x + fw, y + fh), color, 2, cv2.LINE_AA)

            if len(faces) == 0:
                msg, rdy = 'Look at the camera', False
            elif not in_circle:
                msg, rdy = 'Center your face in the circle', False
            elif not ready:
                msg, rdy = 'Hold still…', False
            else:
                msg, rdy = 'Ready — click Enroll', True

            with self.lock:
                self.latest = (vis.copy(), msg, rdy)
                self.last_frame_time = time.time()
            n_iter += 1
            if n_iter % 50 == 1:
                log(f'iter={n_iter} read={read_ms:.0f}ms detect={det_ms:.0f}ms mean={mean:.0f} faces={len(faces)}')

    def _present(self):
        with self.lock:
            item = self.latest
        if self.running and self.last_frame_time and time.time() - self.last_frame_time > 4:
            if self.bridge is not None:
                rc = self.bridge.poll()
                if rc is not None:
                    log(f'watchdog: bridge exited rc={rc}, respawning')
                    self._spawn_bridge()
                else:
                    log('watchdog: bridge alive but no frames >4s, terminating')
                    self.bridge.terminate()
            self.last_frame_time = time.time()
        if item is None:
            return True
        vis, msg, rdy = item
        h, w = vis.shape[:2]
        pb = GdkPixbuf.Pixbuf.new_from_data(
            vis.tobytes(), GdkPixbuf.Colorspace.RGB, False, 8, w, h, w * 3)
        self.pic.set_paintable(Gdk.Texture.new_for_pixbuf(pb))
        self.status.set_text(msg)
        self.btn.set_sensitive(rdy)
        return True

    def _refresh_list(self):
        run_bg(['pkexec', '/usr/local/bin/howdy', 'list'], self._fill_list)

    def _fill_list(self, out):
        while (r := self.listbox.get_first_child()):
            self.listbox.remove(r)
        for line in out.strip().splitlines():
            m = re.match(r'^\s*(\d+)\s+(\d{4}-\d\d-\d\d)\s+([\d:]+)\s+(.*)', line)
            if not m:
                continue
            mid, date, tm, label = m.groups()
            row = Gtk.Box(spacing=10)
            row.add_css_class('model-row')
            lbox = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, hexpand=True)
            lbox.append(Gtk.Label(label=f'#{mid}  {label}', xalign=0))
            lbox.append(Gtk.Label(label=f'{date} {tm}', xalign=0))
            lbox.get_first_child().add_css_class('model-label')
            lbox.get_last_child().add_css_class('model-date')
            row.append(lbox)
            db = Gtk.Button(icon_name='user-trash-symbolic')
            db.add_css_class('destructive-action')
            db.add_css_class('flat')
            db.set_tooltip_text('Remove this model')
            db.connect('clicked', lambda *_, i=mid: self._remove(i))
            row.append(db)
            self.listbox.append(row)

    def _remove(self, mid):
        self.status.set_text(f'Removing model #{mid}…')
        def done(out):
            self._refresh_list()
            self.status.set_text('Model removed')
        run_bg(['pkexec', '/usr/local/bin/howdy', 'remove', str(mid), '-y'], done)

    def _enroll(self, *_):
        label = self.entry.get_text().strip() or 'auto'
        self.btn.set_sensitive(False)
        self.enrolling = True
        self.status.set_text('Enrolling… keep looking at the camera')
        def done(out):
            self.enrolling = False
            ok = 'Added a new model' in out
            self.status.set_text('Enrolled successfully' if ok else 'Enroll failed — try again')
            self.btn.set_sensitive(True)
            self.face_ok_frames = 0
            self._refresh_list()
        run_bg(['pkexec', '/usr/local/bin/howdy', 'add', label], done)

    def _on_close(self, *_):
        self.running = False
        if self.cap:
            self.cap.release()
            self.cap = None
        if self.bridge:
            self.bridge.terminate()
            try:
                self.bridge.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.bridge.kill()
            self.bridge = None
        return False

class App(Gtk.Application):
    def __init__(self):
        super().__init__(application_id='local.faceenroll')
        GLib.set_application_name('Face Models')
    def do_activate(self):
        EnrollWindow(self).present()

if __name__ == '__main__':
    App().run(sys.argv)
