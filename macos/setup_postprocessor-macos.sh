#!/bin/sh

touch data.json
touch nfvsettings.json

ln -s "$(pwd)"/nvfPostprocessor nvfPostprocessor.app/Contents/MacOS/nvfPostprocessor

echo "Postprocessor setup complete."
echo
echo "enter the following in your slicers post processor section:"
echo
echo "$(pwd)/nvfPostprocessor"

