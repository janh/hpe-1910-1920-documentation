#!/usr/bin/env python3

import os
import sys
import mmap
import struct
from collections import namedtuple


FILENAME = ""
EXTRACTION_PATH = ""


FLAG_FREE = 0x80
FLAG_VALID = 0x40
FLAG_INVALID = 0x20
FLAG_HIDE = 0x10
FLAG_DIRECTORY = 0x02
FLAG_READONLY = 0x01


File = namedtuple('File', 'flags year month day hour minute second length parent_block parent_index data_block name')

def parse_file_desc(data):
	parsed = File._make(struct.unpack('>BxxxxxHBBBBBxxxIIHxxI96s', data))
	return parsed._replace(name=parsed.name.split(b'\x00',1)[0].rstrip(b'\xff').decode('ascii'))


FATEntry = namedtuple('FATEntry', 'flags previous next')

def parse_fat_entry(data):
	return FATEntry(int(data[0]), int.from_bytes(data[1:4], 'big'), int.from_bytes(data[5:8], 'big'))


def read_data_blocks(img, data_block):
	while True:
		fat_entry_offset = 0x10000 * (data_block // 63) + 0x8 * (data_block % 63)
		fat_entry = parse_fat_entry(img[fat_entry_offset:fat_entry_offset+0x8])

		if fat_entry.flags != 0x3f:
			return

		offset = 0x10000 * (data_block // 63) + 0x400 * (1 + (data_block % 63))
		yield img[offset:offset+0x400]

		if fat_entry.next == 0xffffff:
			return

		data_block = fat_entry.next


def create_directory(path):
	if not len(EXTRACTION_PATH):
		return

	filename = os.path.join(EXTRACTION_PATH, path)

	try:
		os.mkdir(filename)

	except:
		print("WARNING: directory creation failed!", file=sys.stderr)


def extract_file(img, path, length, data_block):
	if not len(EXTRACTION_PATH):
		return

	filename = os.path.join(EXTRACTION_PATH, path)

	try:
		with open(filename, "xb") as f:

			for block in read_data_blocks(img, data_block):
				if length >= len(block):
					f.write(block)
					length -= len(block)
				else:
					f.write(block[:length])
					return

			if length > 0:
				print("WARNING: failed to read entire file (remaining: {})!".format(length))

	except:
		print("WARNING: file extraction failed!", file=sys.stderr)


def parse_directory(img, parent, parent_block, parent_index, data_block):
	for block in read_data_blocks(img, data_block):
		for i in range(0, 8):
			offset = i * 0x80
			file = parse_file_desc(block[offset:offset+0x80])

			if file.flags & FLAG_VALID == 0 and file.flags & FLAG_INVALID != 0:
				print()

				path = os.path.join(parent, file.name)
				print("File: {}".format(path))

				flags = []
				if file.flags & FLAG_DIRECTORY == 0:
					flags.append("directory")
				if file.flags & FLAG_HIDE == 0:
					flags.append("hide")
				if file.flags & FLAG_READONLY == 0:
					flags.append("read-only")
				print("Flags: {}".format(", ".join(flags) if len(flags) else "-"))

				print("Date: {:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
					file.year, file.month, file.day, file.hour, file.minute, file.second))

				print("Length: {}".format(file.length))

				if file.parent_block != parent_block or file.parent_index != parent_index:
					print("ERROR: Inconsistent parent block or index!", file=sys.stderr)

				if file.flags & FLAG_DIRECTORY == 0:
					create_directory(path)
					parse_directory(img, path, data_block, i, file.data_block)
				else:
					extract_file(img, path, file.length, file.data_block)


def create_extraction_path():
	global EXTRACTION_PATH

	path = os.path.join(os.path.dirname(FILENAME), os.path.basename(FILENAME) + "_extracted")
	try:
		os.mkdir(path)
		EXTRACTION_PATH = path
	except FileExistsError:
		print("WARNING: directory {} already exists, not extracting!".format(path), file=sys.stderr)
	except:
		print("WARNING: failed to create directory for extracting!", file=sys.stderr)


def parse_start(img):
	format_flag_raw = img[0x0:0x4]
	format_flag = int.from_bytes(format_flag_raw, 'big')

	if format_flag != 0x10000400:
		print("ERROR: Unexpected format flag: 0x{}".format(format_flag_raw.hex()), file=sys.stderr)
		sys.exit(1)

	root = parse_file_desc(img[0x400:0x480])
	if (root.flags != 0x3f or
			root.year != 0xffff or root.month != 0xff or root.day != 0xff or
			root.hour != 0xff or root.minute != 0xff or root.second != 0xff or
			root.length != 0xffffffff or
			root.parent_block != 0 or root.parent_index != 0xffff or
			root.data_block != 1 or
			root.name != ''):
		print("ERROR: Unexpected root directory entry: {}".format(root), file=sys.stderr)
		sys.exit()

	print("Root directory entry ok.")

	create_extraction_path()

	parse_directory(img, "", 0, 0, 1)


def main():
	global FILENAME
	FILENAME = sys.argv[1]

	f = open(FILENAME, "r+b")
	img = mmap.mmap(f.fileno(), 0)

	parse_start(img)

	f.close()


if __name__ == '__main__':
	if len(sys.argv) != 2:
		print("invalid arguments")
		sys.exit(1)

	main()
