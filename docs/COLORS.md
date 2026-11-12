# Card colors

Hearts and diamonds use **#D00000**, RGB **(208, 0, 0)**, at full opacity.
Green and blue channels are zero. Card faces use neutral **#FAFAFA** instead of
the previous green-tinted off-white. The felt and mint interface accents keep
their own colors.

The same red appears in the practice card renderer (`desktop/vision.py`), the
observed-card UI (`desktop/qml/Studio.qml`) and the README banner
(`docs/media/hero.svg`). README GIFs and screenshots are regenerated from the app.
GIF palettes reserve the exact red, face and dark ink colors so small red suit
marks are not lost among the larger green interface areas during compression.

The native vision checks exercise recognition against the updated generated
artwork. Existing external table art and user-taught examples are not recolored.
