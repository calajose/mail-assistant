from mail_assistant.cli.parser import get_parser


def test_folders_command_parses():
    args = get_parser().parse_args(["folders"])
    assert args.command == "folders"


def test_scan_with_folder_flag():
    args = get_parser().parse_args(["scan", "--folder", "Spam", "--limit", "5"])
    assert args.command == "scan"
    assert args.folder == "Spam"
    assert args.limit == 5


def test_scan_without_folder_defaults_to_none():
    args = get_parser().parse_args(["scan"])
    assert args.folder is None
