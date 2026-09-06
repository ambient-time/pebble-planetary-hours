.PHONY: test build icon package
PEBBLE ?= pebble
PYTHON ?= python3
TEST_FLAGS = -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined -fno-omit-frame-pointer

test:
	mkdir -p build
	cc $(TEST_FLAGS) test/math.c -o build/math-test
	build/math-test
	node test/solar.test.js
	node test/phone.test.js

build: test
	$(PEBBLE) build
	node test/bundle.test.js

icon:
	magick -background black resources/images/menu-icon.svg -resize 25x25 -threshold 50% -define png:exclude-chunks=date,time resources/images/menu-icon.png

package:
	$(PYTHON) test/package.py --evidence build/evidence
