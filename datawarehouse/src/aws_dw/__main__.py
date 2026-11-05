"""Entry point for python -m aws_dw.cli"""
from .cli import main

if __name__ == "__main__":
    import sys
    sys.exit(main())
