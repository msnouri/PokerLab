"""Entry point for the packaged application (see packaging/README.md)."""
import multiprocessing

from desktop.__main__ import main

if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
