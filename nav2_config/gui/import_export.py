"""Import and Export dialogs for nav2_params.yaml files.

ImportDialog opens a file picker, parses the selected YAML, and calls a
caller-supplied callback so the caller can forward the values to live ROS2
nodes.

ExportDialog opens a file-save dialog and writes a pre-generated YAML string.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from PyQt6.QtWidgets import QFileDialog, QMessageBox, QWidget

from nav2_config.core.yaml_importer import import_yaml
from nav2_config.core.yaml_exporter import save_yaml_to_file

logger = logging.getLogger(__name__)

# File filter string used for both open and save dialogs.
_YAML_FILTER = 'YAML Files (*.yaml *.yml);;All Files (*)'


class ImportDialog:
    """File-open dialog that parses a nav2_params.yaml and calls a callback.

    Usage::

        ImportDialog.run(parent_widget, callback)

    The callback receives ``(filepath, data)`` where *data* is
    ``{node_name: {param_name: value}}``.  The caller is responsible for
    forwarding the values to the running ROS2 nodes.
    """

    @staticmethod
    def run(
        parent: QWidget,
        import_callback: Callable[[str, dict[str, dict[str, Any]]], None],
    ) -> None:
        """Open a file picker, parse the YAML, and invoke *import_callback*.

        Shows an error dialog if the file cannot be parsed.  Does nothing if
        the user cancels the file picker.

        Args:
            parent: Parent widget for the dialog windows.
            import_callback: Called with ``(filepath, parsed_data)`` on success.
        """
        filepath, _ = QFileDialog.getOpenFileName(
            parent,
            'Import Nav2 Parameters',
            '',
            _YAML_FILTER,
        )
        if not filepath:
            return  # User cancelled.

        data = import_yaml(filepath)
        if not data:
            QMessageBox.warning(
                parent,
                'Import Failed',
                f'Could not parse parameter file:\n\n{filepath}\n\n'
                'Make sure it is a valid nav2_params.yaml with node entries\n'
                'under ros__parameters.',
            )
            return

        logger.info(
            'Importing %d nodes from %s',
            len(data),
            filepath,
        )
        import_callback(filepath, data)


class ExportDialog:
    """File-save dialog that writes a YAML string to a chosen path.

    Usage::

        ExportDialog.run(parent_widget, yaml_string)
    """

    @staticmethod
    def run(parent: QWidget, yaml_str: str) -> None:
        """Open a file-save dialog and write *yaml_str* to the chosen path.

        Shows an error dialog if the file cannot be written.  Does nothing if
        the user cancels the file picker.

        Args:
            parent: Parent widget for the dialog windows.
            yaml_str: Pre-generated YAML content to write.
        """
        filepath, _ = QFileDialog.getSaveFileName(
            parent,
            'Export Nav2 Parameters',
            'nav2_params.yaml',
            _YAML_FILTER,
        )
        if not filepath:
            return  # User cancelled.

        try:
            save_yaml_to_file(yaml_str, filepath)
            logger.info('Exported parameters to %s', filepath)
        except OSError as exc:
            logger.error('Export failed: %s', exc)
            QMessageBox.critical(
                parent,
                'Export Failed',
                f'Could not write file:\n\n{filepath}\n\n{exc}',
            )
