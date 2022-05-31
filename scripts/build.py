#!/usr/bin/env python3

import io
import os
import sys
import struct
import py7zr


try:
	import crcmod.predefined
	calculate_crc = crcmod.predefined.mkCrcFun('xmodem')

except:
	def calculate_crc(data):
		poly = 0x1021
		crc = 0

		for b in data:
			crc = crc ^ (b << 8)

			for _ in range(0, 8):
				crc = crc << 1
				if crc & 0x10000:
					crc = (crc ^ poly) & 0xffff

		return crc


def create_main_header(product_id, device_id):
	img = bytearray(6180)

	# Version
	struct.pack_into('>I', img, 0x0, 0x1)

	# Product ID and Device ID
	struct.pack_into('>II', img, 0x8, product_id, device_id)

	# Date
	struct.pack_into('>HBBxBBB', img, 0x10, 1970, 1, 1, 0, 0, 0)

	return img


def add_main_header_file(img, data, type_mask):
	i = int.from_bytes(img[0x4:0x8], 'big')
	off = 0x20 + i*24

	# File type
	img[off+0x0:off+0x4] = data[0x8:0xc]

	# Offset
	struct.pack_into('>I', img, off+0x4, len(img))

	# Length
	struct.pack_into('>I', img, off+0x8, int.from_bytes(data[0x148:0x14c], 'big') + 340)

	# File CRC
	img[off+0xc:off+0x10] = data[0x14c:0x150]

	# Version
	img[off+0x10:off+0x14] = data[0xc:0x10]

	# Type mask
	struct.pack_into('>I', img, off+0x14, type_mask)

	# increase number of files
	struct.pack_into('>I', img, 0x4, i+1)

	img += data


def finalize_main_header(img):
	# Package CRC and Package Flag
	struct.pack_into('>HH', img, 0x18, calculate_crc(img[0x1824:]), 0x2)

	# Length
	struct.pack_into('>I', img, 0x1c, len(img)-0x1824)

	# Header CRC
	struct.pack_into('>I', img, 0x1820, calculate_crc(img[0:0x1820]))


def create_file(path, file_type, product_id, device_id, version, version_offset, compressed):
	data = bytearray(340)

	if compressed:
		b = io.BytesIO()
		with py7zr.SevenZipFile(b, 'w', filters=[{'id': py7zr.FILTER_LZMA}]) as z:
			z.set_encoded_header_mode(False)
			z.write(path, os.path.basename(path))
		content = b.getvalue()
	else:
		with open(path, 'rb') as f:
			content = f.read()

	length = len(content)

	# File type
	struct.pack_into('>I', data, 0x8, file_type)

	# Version
	struct.pack_into('>I', data, 0xc, version)

	# Product ID and Device ID
	struct.pack_into('>II', data, 0x10, product_id, device_id)

	# Unknown length
	struct.pack_into('>I', data, 0x18, length-6 if compressed else length)

	# Version offset
	struct.pack_into('>I', data, 0x1c, version_offset)

	# Date
	struct.pack_into('>HBBxBBB', data, 0x20, 1970, 1, 1, 0, 0, 0)

	# Description
	struct.pack_into('224s', data, 0x68, os.path.basename(path).encode('ascii'))

	# Length
	struct.pack_into('>I', data, 0x148, length)

	# File CRC
	struct.pack_into('>I', data, 0x14c, calculate_crc(content))

	# Compression type
	struct.pack_into('>I', data, 0x150, 0x2 if compressed else 0xffffffff)

	# Header CRC
	struct.pack_into('>I', data, 0x4, calculate_crc(data[0x8:0x154]))

	return data + content


def main():
	filename = sys.argv[1]

	product_id = 0x3c010501
	device_id = 0x00010026

	img = create_main_header(product_id, device_id)

	#add_main_header_file(img, create_file("data/basic", 0x05000001, product_id, 0x1, 0x00010016, 0x440, False), 0xffffffff)
	#add_main_header_file(img, create_file("data/extend", 0x05000000, product_id, 0x1, 0x00010016, 0x440, True), 0x1)
	#add_main_header_file(img, create_file("data/app", 0x04000000, product_id, device_id, 0x1, 0xffffffff, True), 0x1)

	add_main_header_file(img, create_file("openwrt-realtek-rtl838x-hpe_1920-16g-initramfs-kernel.bin", 0x04000000, product_id, device_id, 0x1, 0xffffffff, True), 0x1)

	finalize_main_header(img)

	f = open(filename, "xb")
	f.write(img)
	f.close()


if __name__ == '__main__':
	if len(sys.argv) != 2:
		print("invalid arguments")
		sys.exit(1)

	main()
