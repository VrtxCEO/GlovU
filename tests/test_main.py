import unittest
from unittest.mock import Mock, patch

import main as main_module


class MainEntryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.logger = Mock()

    def test_first_run_launches_installed_exe_after_install(self) -> None:
        with patch.object(main_module, "get_logger", return_value=self.logger), \
             patch.object(main_module, "_is_admin", return_value=True), \
             patch.object(main_module, "_self_install_exe") as self_install, \
             patch.object(main_module, "_do_install") as do_install, \
             patch.object(main_module, "_launch_installed_exe") as launch_installed, \
             patch.object(main_module, "run") as run_runtime:
            main_module.first_run()

        self_install.assert_called_once_with()
        do_install.assert_called_once_with(silent=True)
        launch_installed.assert_called_once_with(["--run"])
        run_runtime.assert_not_called()

    def test_main_entry_blocks_duplicate_launch(self) -> None:
        with patch.object(main_module, "configure_logging"), \
             patch.object(main_module, "get_logger", return_value=self.logger), \
             patch.object(main_module, "_acquire_single_instance", return_value=False), \
             patch.object(main_module, "_show_already_running_notice") as show_notice:
            rc = main_module.main_entry([])

        self.assertEqual(rc, 0)
        show_notice.assert_called_once_with()

    def test_main_entry_refreshes_installed_copy_for_external_launcher(self) -> None:
        with patch.object(main_module, "configure_logging"), \
             patch.object(main_module, "get_logger", return_value=self.logger), \
             patch.object(main_module, "_acquire_single_instance", return_value=True), \
             patch.object(main_module, "_is_running_from_install_dir", return_value=False), \
             patch.object(main_module, "_is_installed", return_value=True), \
             patch.object(main_module, "_self_install_exe") as self_install, \
             patch.object(main_module, "_do_install") as do_install, \
             patch.object(main_module, "_launch_installed_exe") as launch_installed, \
             patch.object(main_module.sys, "frozen", True, create=True):
            rc = main_module.main_entry([])

        self.assertEqual(rc, 0)
        self_install.assert_called_once_with()
        do_install.assert_called_once_with(silent=True)
        launch_installed.assert_called_once_with(["--run"])

    def test_main_entry_first_run_prompt_starts_install(self) -> None:
        with patch.object(main_module, "configure_logging"), \
             patch.object(main_module, "get_logger", return_value=self.logger), \
             patch.object(main_module, "_acquire_single_instance", return_value=True), \
             patch.object(main_module, "_is_installed", return_value=False), \
             patch.object(main_module, "_prompt_install", return_value=True), \
             patch.object(main_module, "first_run") as first_run:
            rc = main_module.main_entry([])

        self.assertEqual(rc, 0)
        first_run.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
