#!/usr/bin/env python3

import os
import sys
import mmap


FILENAME = None
DIR_CREATED = False


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


def check_crc(crc, data):
	crc_actual = calculate_crc(data)

	if crc == crc_actual:
		return "{:#04x}".format(crc), True
	else:
		return "{:#04x} != {:#04x}".format(crc, crc_actual), False


def get_int(data):
	return int.from_bytes(data, 'big')


def get_date(data):
	return "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(
		int.from_bytes(data[0:2], 'big'), int(data[2]), int(data[3]),
		int(data[5]), int(data[6]), int(data[7]))


def get_file_type(data):
	val = data.hex()
	desc = None

	if val == '04000000':
		desc = "Application"
	elif val == '05000000':
		desc = "Extended BootWare"
	elif val == '05000001':
		desc = "Basic BootWare"

	if desc:
		return "0x{} ({})".format(val, desc)
	return "0x{}".format(val)


def get_compression_type(data):
	val = data.hex()
	desc = None
	ext = ''

	if val == 'ffffffff':
		desc = "uncompressed"
	elif val == '00000001':
		desc = "ARJ"
		ext = 'arj'
	elif val == '00000002':
		desc = "7z"
		ext = '7z'

	if desc:
		return "0x{} ({})".format(val, desc), ext
	return "0x{}".format(val), ext


def parse_header(img):
	print("Main header")

	print("Version: 0x{}".format(img[0x0:0x4].hex()))

	print("Number of files: {}".format(get_int(img[0x4:0x8])))

	print("Product ID: 0x{}".format(img[0x8:0xc].hex()))
	print("Device ID: 0x{}".format(img[0xc:0x10].hex()))

	print("Date: {}".format(get_date(img[0x10:0x18])))

	package_crc = check_crc(get_int(img[0x18:0x1a]), img[0x1824:])
	print("Package CRC: {}".format(package_crc[0]))
	if not package_crc[1]:
		print("ERROR: invalid package CRC!", file=sys.stderr)

	print("Length: {}".format(get_int(img[0x1c:0x20])))

	header_crc = check_crc(get_int(img[0x1820:0x1824]), img[:0x1820])
	print("Header CRC: {}".format(header_crc[0]))
	if not header_crc[1]:
		print("ERROR: invalid main header CRC!", file=sys.stderr)

	for i in range(0, 128):
		offset = 0x20+i*24
		desc = img[offset:offset+24]
		if not all(x == 0 for x in desc):
			parse_file(i, desc, img)


def parse_file(i, desc, img):
	print()
	print("File descriptor {}".format(i))

	desc_type = get_int(desc[0x0:0x4])
	desc_offset = get_int(desc[0x4:0x8])
	desc_length = get_int(desc[0x8:0xc])
	desc_file_crc = get_int(desc[0xc:0x10])
	desc_version = get_int(desc[0x10:0x14])

	print("Type mask: {}".format(desc[0x14:0x18].hex()))

	print("File header")

	file_offset = desc_offset+340
	head = img[desc_offset:file_offset]

	header_crc = check_crc(get_int(head[0x4:0x8]), head[0x8:0x154])
	print("Header CRC: {}".format(header_crc[0]))
	if not header_crc[1]:
		print("ERROR: invalid file header CRC!", file=sys.stderr)

	file_type_raw = head[0x8:0xc]
	print("Type: {}".format(get_file_type(file_type_raw)))
	if get_int(file_type_raw) != desc_type:
		print("ERROR: inconsistent file type!", file=sys.stderr)

	version_raw = head[0xc:0x10]
	print("Version: 0x{}".format(version_raw.hex()))
	if get_int(version_raw) != desc_version:
		print("ERROR: inconsistent file version!", file=sys.stderr)

	print("Product ID: 0x{}".format(head[0x10:0x14].hex()))
	print("Device ID: 0x{}".format(head[0x14:0x18].hex()))

	length_unpadded = get_int(head[0x18:0x1c])
	print("Length without padding: {}".format(length_unpadded))

	print("Version offset: 0x{}".format(head[0x1c:0x20].hex()))

	print("Date: {}".format(get_date(head[0x20:0x28])))

	print("Description: {}".format(head[0x68:0x148].decode('ascii').rstrip('\x00')))

	length = get_int(head[0x148:0x14c])
	print("Length: {}".format(length))
	if length != desc_length - 340:
		print("ERROR: inconsistent file length!", file=sys.stderr)

	expected_length = length_unpadded - length_unpadded % 8 + 8 if length_unpadded % 8 != 0 else length_unpadded
	print("Padding size: {}".format(length-length_unpadded))
	if expected_length != length:
		print("ERROR: inconsistent file length!", file=sys.stderr)

	file = img[file_offset:file_offset+length]
	file_crc_int = get_int(head[0x14c:0x150])
	file_crc = check_crc(file_crc_int, file)
	print("File CRC: {}".format(file_crc[0]))
	if not file_crc[1]:
		print("ERROR: invalid file CRC!", file=sys.stderr)
	if file_crc_int != desc_file_crc:
		print("ERROR: inconsistent file CRC!", file=sys.stderr)

	comp = get_compression_type(head[0x150:0x154])
	print("Compression: {}".format(comp[0]))

	filepath = os.path.join(os.path.dirname(FILENAME), os.path.basename(FILENAME) + "_extracted")
	filename = os.path.join(filepath, "{}_{}_{}".format(i, file_offset, file_type_raw.hex()))
	if comp[1] != '':
		filename += ".{}".format(comp[1])

	global DIR_CREATED
	if not DIR_CREATED:
		try:
			os.mkdir(filepath)
			DIR_CREATED = True
		except FileExistsError:
			print("WARNING: directory {} already exists, not extracting!".format(filepath), file=sys.stderr)
			return
		except:
			print("WARNING: file extraction failed!", file=sys.stderr)
			return

	try:
		f = open(filename, "xb")
		f.write(file)
		f.close()
	except:
		print("WARNING: file extraction failed!", file=sys.stderr)
		return


def main():
	global FILENAME
	FILENAME = sys.argv[1]

	f = open(FILENAME, "r+b")
	img = mmap.mmap(f.fileno(), 0)

	parse_header(img)

	f.close()


if __name__ == '__main__':
	if len(sys.argv) != 2:
		print("invalid arguments")
		sys.exit(1)

	main()
