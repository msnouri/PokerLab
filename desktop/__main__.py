"""Launch Vision Studio; --lab opens the Agent Lab; --classic keeps the first workbench."""
import argparse


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--classic',action='store_true')
    parser.add_argument('--lab',action='store_true',help='Agent Lab: play, coach, ranges and policy comparison')
    parser.add_argument('--screen',action='store_true',help='Mac screen capture and local MP4 recording')
    parser.add_argument('--seed',type=int,default=None,help='Fix the Agent Lab deal order')
    parser.add_argument('--screenshot',default=None,help='Agent Lab: save one frame and exit')
    parser.add_argument('--backend',choices=['auto','vision','native','subprocess'],default='auto')
    args=parser.parse_args()
    if args.screen and (args.lab or args.classic):parser.error('--screen opens Vision Studio; use it without --lab or --classic')
    if args.lab:
        from .lab import main as launch
        launch(args.screenshot,args.seed)
    elif args.classic:
        from .app import main as launch
        launch()
    else:
        from .studio import main as launch
        launch(args.backend,start_page=4 if args.screen else 0)


if __name__=='__main__':main()
