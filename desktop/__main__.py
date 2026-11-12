"""Launch the macOS Vision Studio; --classic retains the research workbench."""
import argparse


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--classic',action='store_true')
    parser.add_argument('--backend',choices=['auto','vision','native','subprocess'],default='auto')
    args=parser.parse_args()
    if args.classic:
        from .app import main as launch
        launch()
    else:
        from .studio import main as launch
        launch(args.backend)


if __name__=='__main__':main()
