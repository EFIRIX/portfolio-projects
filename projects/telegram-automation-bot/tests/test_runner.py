from bot.runner import command_arg


def test_command_arg_plain():
    assert command_arg("/set_archive_group -1001", "set_archive_group") == "-1001"


def test_command_arg_with_bot_mention():
    assert command_arg("/set_archive_group@aerixseebot -1001", "set_archive_group") == "-1001"


def test_command_arg_without_argument():
    assert command_arg("/set_archive_group@aerixseebot", "set_archive_group") == ""


def test_command_arg_empty():
    assert command_arg("", "set_archive_group") == ""
