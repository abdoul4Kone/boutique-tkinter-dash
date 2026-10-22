"""Régressions du passage entre threads, sans écran ni base de données."""
from concurrent.futures import ThreadPoolExecutor
import itertools
import queue
import threading
import unittest
from unittest.mock import patch

from app.runtime import Application


class Owner:
    def __init__(self):
        self.exists = True

    def winfo_exists(self):
        return self.exists


class Control(Owner):
    def __init__(self, state='normal'):
        super().__init__()
        self.state = state

    def cget(self, key):
        return self.state

    def configure(self, **values):
        self.state = values['state']


class Root:
    def __init__(self):
        self.callbacks = []

    def after(self, *args):
        self.callbacks.append(args[1])

    def after_idle(self, callback):
        self.callbacks.append(callback)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.app = Application.__new__(Application)
        self.app.root = Root()
        self.app.executor = ThreadPoolExecutor(max_workers=1)
        self.app.queue = queue.Queue()
        self.app.jobs = {}
        self.app.sequence = itertools.count()
        self.app.closing = False
        self.app.auth_pending = None
        self.owner = Owner()
        self.events = []
        self.identity = patch('app.runtime.current_user_id', return_value=7)
        self.identity.start()
        self.addCleanup(self.identity.stop)
        self.addCleanup(self.app.executor.shutdown, wait=True)

    def finish(self):
        token, future = self.app.queue.get(timeout=3)
        self.app.queue.put((token, future))
        self.app.poll()

    def success(self, value):
        self.events.append(('success', value, threading.get_ident()))

    def failure(self, error):
        self.events.append(('error', str(error), threading.get_ident()))

    def test_operation_runs_in_worker_and_callback_in_caller(self):
        caller = threading.get_ident()
        self.app.submit(self.owner, threading.get_ident, self.success, self.failure)
        self.finish()
        self.assertNotEqual(self.events[0][1], caller)
        self.assertEqual(self.events[0][2], caller)
        self.assertFalse(self.owner._task_busy)
        self.assertEqual(self.app.jobs, {})

    def test_duplicate_submission_is_refused_until_completion(self):
        gate = threading.Event()
        self.app.submit(self.owner, lambda: gate.wait(2), self.success, self.failure)
        try:
            self.assertFalse(self.app.submit(self.owner, lambda: 2, self.success, self.failure))
            self.assertEqual(len(self.app.jobs), 1)
        finally:
            gate.set()
        self.finish()
        self.assertEqual(len(self.events), 1)

    def test_control_states_are_restored_even_after_error(self):
        enabled, disabled = Control(), Control('disabled')
        def fail():
            raise ValueError('Erreur de démonstration')
        self.app.submit(self.owner, fail, self.success, self.failure, (enabled, disabled))
        self.assertEqual(enabled.state, 'disabled')
        self.finish()
        self.assertEqual(enabled.state, 'normal')
        self.assertEqual(disabled.state, 'disabled')
        self.assertEqual(self.events[0][:2], ('error', 'Erreur de démonstration'))

    def test_destroyed_page_cannot_receive_a_late_result(self):
        control = Control()
        self.app.submit(self.owner, lambda: 'ancien écran', self.success, self.failure, (control,))
        self.owner.exists = False
        self.finish()
        self.assertEqual(self.events, [])
        self.assertEqual(self.app.jobs, {})

    def test_changed_account_discards_private_result(self):
        self.app.submit(self.owner, lambda: 'données du client 7', self.success, self.failure)
        destinations = []
        self.app.navigate = lambda *args, **kwargs: destinations.append((args, kwargs))
        with patch('app.runtime.current_user_id', return_value=8):
            self.finish()
        self.assertEqual(self.events, [])
        self.assertEqual(destinations[0][0], ('connexion',))

    def test_authentication_can_change_identity_and_releases_navigation(self):
        self.app.submit(self.owner, lambda: True, self.success, self.failure, auth=True)
        self.assertIs(self.app.auth_pending, self.owner)
        with patch('app.runtime.current_user_id', return_value=8):
            self.finish()
        self.assertIsNone(self.app.auth_pending)
        self.assertEqual(self.events[0][:2], ('success', True))

    def test_authentication_error_releases_navigation(self):
        def fail():
            raise OSError('Session indisponible')
        self.app.submit(self.owner, fail, self.success, self.failure, auth=True)
        self.finish()
        self.assertIsNone(self.app.auth_pending)
        self.assertEqual(self.events[0][0], 'error')

    def test_destroyed_authentication_page_releases_navigation(self):
        self.app.submit(self.owner, lambda: False, self.success, self.failure, auth=True)
        self.owner.exists = False
        self.finish()
        self.assertIsNone(self.app.auth_pending)
        self.assertEqual(self.events, [])

    def test_scroll_is_restored_after_layout_settles_and_not_on_a_new_page(self):
        from types import SimpleNamespace
        positions = []
        canvas = SimpleNamespace(bbox=lambda *args: (0, 0, 600, 1200),
                                 winfo_width=lambda: 600, winfo_height=lambda: 480,
                                 yview_moveto=positions.append)
        observer = SimpleNamespace(pending=True)
        container = SimpleNamespace(_responsive=observer)
        view = SimpleNamespace(scroll=SimpleNamespace(_parent_canvas=canvas), columns=2,
                               controls=container, filters=container, cards=container)
        self.app.page = self.owner
        self.app.restore_scroll(self.owner, view, .35)
        self.app.root.callbacks.pop(0)()
        self.assertEqual(positions, [])
        canvas.bbox = lambda *args: (0, 0, 600, 1900)
        observer.pending = None
        self.app.root.callbacks.pop(0)()
        self.assertEqual(positions, [])
        self.app.root.callbacks.pop(0)()
        self.assertEqual(positions, [.35])
        self.app.restore_scroll(self.owner, view, .60)
        self.app.page = Owner()
        self.app.root.callbacks.pop(0)()
        self.assertEqual(positions, [.35])


if __name__ == '__main__':
    unittest.main()
