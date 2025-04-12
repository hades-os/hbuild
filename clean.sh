#!/bin/bash

dirs=("sources" "builds" "system_prefix" "system_files" "tools" "packages" "works")

for dir in ${dirs[@]}; do
  mkdir -pv ${dir}
done

cp "build_files/cross_file.txt" "sources/cross_file.txt"