#!/bin/bash
# llvm-nm that strips the Mach-O leading underscore (DMC100-Doom converter wants plain names on macOS).
exec llvm-nm "$@" | sed -E "s/^_//"
