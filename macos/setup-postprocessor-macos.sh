#!/bin/sh

touch nfvsettings.json

ln -s "$(pwd)"/nvfPostprocessor nvfPostprocessor.app/Contents/MacOS/nvfPostprocessor

rm -rf ~/Applications/nvfPostprocessor.app
mv nvfPostprocessor.app ~/Applications/

echo "Postprocessor setup complete."
echo
echo "enter the following in your slicers post processor section:"
echo
echo "$(pwd)/nvfPostprocessor"

