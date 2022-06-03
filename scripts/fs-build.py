#!/usr/bin/env python3

import os
import sys
import mmap
import struct
from collections import namedtuple


FLAG_FREE = 0x80
FLAG_VALID = 0x40
FLAG_INVALID = 0x20
FLAG_HIDE = 0x10
FLAG_DIRECTORY = 0x02
FLAG_READONLY = 0x01


DIR_BLOCK = 1
DIR_COUNT = 0

NEXT_DATA_BLOCK = 2


File = namedtuple('File', 'flags year month day hour minute second length parent_block parent_index data_block name')

def write_file_entry(img, offset, file):
	struct.pack_into('>B', img, offset, file.flags)
	struct.pack_into('>HBBBBB', img, offset+0x6, file.year, file.month, file.day, file.hour, file.minute, file.second)
	struct.pack_into('>IIH', img, offset+0x10, file.length, file.parent_block, file.parent_index)
	struct.pack_into('>I96s', img, offset+0x1c, file.data_block, file.name)


def get_fat_entry_offset(block):
	return 0x10000 * (block // 63) + 0x8 * (block % 63)


def get_block_offset(block):
	return 0x10000 * (block // 63) + 0x400 * (1 + (block % 63))


def create_root_directory():
	img = bytearray(b'\xff') * 0x10000

	# Format flag
	img[0:4] = b'\x10\x00\x04\x00'

	# FAT entry for block 1 (contains first file entries of root directory)
	img[8:9] = b'\x3f'

	root_dir = File(flags=0xff & ~(FLAG_FREE | FLAG_VALID),
		year=0xffff, month=0xff, day=0xff, hour=0xff, minute=0xff, second=0xff,
		length=0xffffffff, parent_block=0, parent_index=0xffff, data_block=1,
		name=b'\xff'*96)

	write_file_entry(img, 0x400, root_dir)

	return img


def write_file(img, filename, path):
	global DIR_BLOCK, DIR_COUNT, NEXT_DATA_BLOCK

	data_block = NEXT_DATA_BLOCK
	length = 0

	# write file data
	with open(path, 'rb') as f:
		first = True

		while True:
			data = f.read(0x400)
			if not first and len(data) == 0:
				break

			length += len(data)

			# previous FAT entry right pointer
			if not first:
				img[fat_entry_offset+5:fat_entry_offset+8] = NEXT_DATA_BLOCK.to_bytes(3, 'big')

			fat_entry_offset = get_fat_entry_offset(NEXT_DATA_BLOCK)
			if fat_entry_offset >= len(img):
				img += bytearray(b'\xff') * 0x10000

			# FAT entry left pointer
			img[fat_entry_offset:fat_entry_offset+1] = b'\x3f'
			if not first:
				img[fat_entry_offset+1:fat_entry_offset+4] = (NEXT_DATA_BLOCK-1).to_bytes(3, 'big')

			offset = get_block_offset(NEXT_DATA_BLOCK)

			img[offset:offset+len(data)] = data

			first = False
			NEXT_DATA_BLOCK += 1

	# create new file entries block if necessary
	if DIR_COUNT == 8:
		# update previous FAT entry right pointer
		fat_entry_offset = get_fat_entry_offset(DIR_BLOCK)
		img[fat_entry_offset+5:fat_entry_offset+8] = NEXT_DATA_BLOCK.to_bytes(3, 'big')

		# new FAT entry left pointer
		fat_entry_offset = get_fat_entry_offset(NEXT_DATA_BLOCK)
		if fat_entry_offset >= len(img):
			img += bytearray(b'\xff') * 0x10000
		img[fat_entry_offset:fat_entry_offset+1] = b'\x3f'
		img[fat_entry_offset+1:fat_entry_offset+4] = DIR_BLOCK.to_bytes(3, 'big')

		DIR_BLOCK = NEXT_DATA_BLOCK
		DIR_COUNT = 0
		NEXT_DATA_BLOCK += 1

	# now write file entry
	file = File(flags=0xff & ~(FLAG_FREE | FLAG_VALID),
		year=1970, month=1, day=1, hour=0, minute=0, second=0,
		length=length, parent_block=0, parent_index=0, data_block=data_block,
		name=filename.encode('ascii'))

	offset = get_block_offset(DIR_BLOCK) + 0x80 * DIR_COUNT
	write_file_entry(img, offset, file)

	DIR_COUNT += 1


def main():
	filename = sys.argv[1]

	img = create_root_directory()

	write_file(img, "kernel.bin", "openwrt-kernel-image.bin")

	with open(filename, "xb") as f:
		f.write(img)
		f.close()


if __name__ == '__main__':
	if len(sys.argv) != 2:
		print("invalid arguments")
		sys.exit(1)

	main()
