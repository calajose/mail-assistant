from .cli.parser import get_parser
from .cli.configure import run_configure
from .cli.scan import run_scan
from .cli.report import run_report
from .cli.clean import run_clean
from .cli.folders import run_folders

def main():
    parser = get_parser()
    args = parser.parse_args()

    if args.command == "configure":
        run_configure(model_only=args.model_only)
    elif args.command == "scan":
        run_scan(args.limit, args.no_llm, args.folder, args.process_all, args.force_llm)
    elif args.command == "report":
        run_report()
    elif args.command == "clean":
        run_clean(args.folder, args.yes, args.process_all)
    elif args.command == "folders":
        run_folders()
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
