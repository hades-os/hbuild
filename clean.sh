#!/bin/bash

dirs=("sources" "builds" "system_prefix" "system_files" "tools" "packages")

for dir in ${dirs[@]}; do
  rm -rf ${dir}
  mkdir ${dir}
done

cp "build_files/cross_file.txt" "sources/cross_file.txt"