# Copyright 2025-2026 Sutharsan
# SPDX-License-Identifier: Apache-2.0

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
from rclpy.executors import MultiThreadedExecutor
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from nav2_config.node import Nav2ConfigNode
from nav2_config.gui.main_window import MainWindow, _load_settings
from nav2_config.gui.theme import apply_theme
from nav2_config.gui.icons import app_icon
from nav2_config.types.params import load_schema

logging.basicConfig(
    level=logging.INFO,
    format='[%(levelname)s] %(name)s: %(message)s',
)
logger = logging.getLogger(__name__)


def _spin_node(node: Nav2ConfigNode) -> None:
    """Target function for the ROS2 background thread.

    Uses MultiThreadedExecutor so that service response callbacks can be
    processed on a separate thread while a timer callback is waiting for a
    future.  This prevents deadlocks in Nav2ParamClient._call().
    """
    executor = MultiThreadedExecutor()
    executor.add_node(node)
    try:
        executor.spin()
    except Exception:
        logger.exception('ROS2 spin thread raised an exception')


def main() -> None:
    """Launch the nav2_config GUI with a co-running ROS2 node."""
    # 1. Initialise ROS2
    rclpy.init(args=sys.argv)
    node = Nav2ConfigNode()

    try:
        schema = load_schema()
        node.set_schema(schema)
        logger.info('Loaded %d param schema entries', len(schema))
    except Exception:
        logger.exception('Failed to load nav2_params.json -- params will show live values only')

    # 2. Start ROS2 spin on a background daemon thread
    ros_thread = threading.Thread(target=_spin_node, args=(node,), daemon=True)
    ros_thread.start()
    logger.info('ROS2 spin thread started (tid=%s)', ros_thread.native_id)

    # 3. Create Qt application
    app = QApplication(sys.argv)
    apply_theme(app)
    app.setWindowIcon(app_icon())

    # 4. Show Load Config dialog
    from nav2_config.gui.load_dialog import LoadConfigDialog
    from nav2_config.core.config_file import ConfigFile

    settings = _load_settings()
    recent_files: list[str] = settings.get('recent_files', [])

    load_dialog = LoadConfigDialog(recent_files=recent_files)
    config_file: ConfigFile | None = None

    if load_dialog.exec():
        filepath = load_dialog.selected_filepath()
        if filepath:
            try:
                config_file = ConfigFile(filepath)
                config_file.load()
                logger.info('Config file loaded: %s', filepath)
            except Exception as exc:
                logger.warning('Failed to load config file %s: %s', filepath, exc)
                config_file = None

    # 5. Open main window
    window = MainWindow(node, config_file=config_file)
    window.show()

    # 6. Ctrl+C handler
    def _sigint_handler(signum: int, frame: object) -> None:  # noqa: ANN001
        logger.info('SIGINT received -- closing GUI')
        window.close()

    signal.signal(signal.SIGINT, _sigint_handler)

    sigint_timer = QTimer()
    sigint_timer.setInterval(500)
    sigint_timer.timeout.connect(lambda: None)
    sigint_timer.start()

    # 7. Run Qt event loop
    exit_code = app.exec()
    logger.info('Qt event loop exited with code %d', exit_code)

    # 8. Clean shutdown
    logger.info('Shutting down ROS2 node')
    node.destroy_node()
    rclpy.shutdown()

    sys.exit(exit_code)


if __name__ == '__main__':
    main()
