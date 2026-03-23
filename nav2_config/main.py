"""Entry point for nav2_config.

Wires together:
  - rclpy (ROS2 Python client) running on a background daemon thread
  - PyQt6 QApplication running on the main thread
  - SignalBridge connecting the two without shared mutable state

Usage:
    ros2 run nav2_config gui
"""

import logging
import signal
import sys
import threading

import rclpy
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from nav2_config.node import Nav2ConfigNode
from nav2_config.gui.main_window import MainWindow
from nav2_config.gui.theme import apply_theme

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def _spin_node(node: Nav2ConfigNode) -> None:
    """Target function for the ROS2 background thread.

    Calls rclpy.spin() which blocks until the node is shut down.
    Runs as a daemon so the process exits when Qt's main thread ends.
    """
    try:
        rclpy.spin(node)
    except Exception:
        logger.exception('ROS2 spin thread raised an exception')


def main() -> None:
    """Launch the nav2_config GUI with a co-running ROS2 node."""
    # ── 1. Initialise ROS2 ─────────────────────────────────────────────
    rclpy.init(args=sys.argv)
    node = Nav2ConfigNode()

    # ── 2. Start ROS2 spin on a background daemon thread ───────────────
    # Daemon=True means the thread is killed automatically when the main
    # (Qt) thread exits — no explicit join needed.
    ros_thread = threading.Thread(target=_spin_node, args=(node,), daemon=True)
    ros_thread.start()
    logger.info('ROS2 spin thread started (tid=%s)', ros_thread.native_id)

    # ── 3. Create Qt application ────────────────────────────────────────
    app = QApplication(sys.argv)
    apply_theme(app)

    window = MainWindow(node)
    window.show()

    # ── 4. Ctrl+C: close Qt window → triggers clean shutdown ───────────
    # Qt intercepts SIGINT by default; restore Python behaviour so Ctrl+C
    # reaches our handler and gracefully closes the window.
    def _sigint_handler(signum: int, frame: object) -> None:  # noqa: ANN001
        logger.info('SIGINT received — closing GUI')
        window.close()

    signal.signal(signal.SIGINT, _sigint_handler)

    # Allow Python's signal handler to fire every 500 ms even while Qt
    # is blocking in app.exec() (Qt doesn't yield to Python otherwise).
    sigint_timer = QTimer()
    sigint_timer.setInterval(500)
    sigint_timer.timeout.connect(lambda: None)  # forces return to Python
    sigint_timer.start()

    # ── 5. Run Qt event loop (blocks until window is closed) ───────────
    # QApplication.exec() is PyQt6's event loop — unrelated to shell exec.
    exit_code = app.exec()  # noqa: S603 (not a shell call)
    logger.info('Qt event loop exited with code %d', exit_code)

    # ── 6. Clean shutdown ───────────────────────────────────────────────
    logger.info('Shutting down ROS2 node')
    node.destroy_node()
    rclpy.shutdown()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
