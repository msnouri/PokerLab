"""Seat names under the engine convention used throughout this repository.

Three or more players: seat 0 is the small blind, seat 1 the big blind and the
last seat is the button. Heads-up: seat 1 is the button and small blind.
"""
NAMES=('BTN','CO','HJ','LJ','UTG+2','UTG+1','UTG')


def position_name(seat,players):
    if players==2:return 'BTN/SB' if seat==1 else 'BB'
    if seat==0:return 'SB'
    if seat==1:return 'BB'
    off=players-1-seat
    if seat==2 and off>0:return 'UTG'
    return NAMES[off]


def seats_off_button(seat,players):
    """0 for the button; None for the blinds (and for the heads-up big blind)."""
    if players==2:return 0 if seat==1 else None
    return None if seat<2 else players-1-seat
