from cookie_refresher.cli import build_parser


def test_cli_requires_mode():
    parser = build_parser()
    args = parser.parse_args([])
    assert args.once is False
    assert args.schedule is False
