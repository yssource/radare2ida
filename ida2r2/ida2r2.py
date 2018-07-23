#!/usr/bin/env python

""" Export IDB from IDA into a radare2 script

$ idb2r2.py -h

usage: idb2r2.py [-h] (-idb IDB_FILE | -idc IDC_FILE) -o OUT_FILE [-nc | -nf]

Export IDB or IDC from IDA into a radare2 initialization script

optional arguments:
  -h, --help            show this help message and exit
  -idb IDB_FILE, --IDBFile IDB_FILE
                        Path to the IDB file
  -idc IDC_FILE, --IDCFile IDC_FILE
                        Path to the IDC file
  -o OUT_FILE, --OutputFile OUT_FILE
                        Export to a specified file path
  -nc, --no-comments    Don't convert comments
  -nf, --no-functions   Don't convert functions

"""

__author__ = "Itay Cohen (@megabeets_), Maxime Morin (@maijin), Sergi Alvarez (@pancake)"


import argparse
import idb
import sys
import re
import base64


def get_args():
    ''' Handle arguments using argparse
    '''

    arg_parser = argparse.ArgumentParser(
        description="Export IDB or IDC from IDA into a radare2 initialization script")

    arg_group_files = arg_parser.add_mutually_exclusive_group(required=True)

    arg_group_files.add_argument("-idb", "--IDBFile",
                            action="store",
                            dest="idb_file",
                            help="Path to the IDB file")

    arg_group_files.add_argument("-idc", "--IDCFile",
                            action="store",
                            dest="idc_file",
                            help="Path to the IDC file")

    arg_parser.add_argument("-o", "--OutputFile",
                            action="store",
                            dest="out_file",
                            required=True,
                            help="Export to a specified file path")

    arg_group = arg_parser.add_mutually_exclusive_group()

    arg_group.add_argument("-nc", "--no-comments",
                           dest="is_comments",
                           action="store_false",
                           help="Don't convert comments")

    arg_group.add_argument("-nf", "--no-functions",
                           dest="is_functions",
                           action="store_false",
                           help="Don't convert functions")

    arg_parser.set_defaults(is_comments=True, is_functions=True)

    args = arg_parser.parse_args()
    return args



###
# IDB Parsing
#

def idb2r2_comments(api, textseg):
    ''' Convert comments from a specific text segments in the IDB
    '''

    for ea in range(textseg, api.idc.SegEnd(textseg)):
        try:
            flags = api.ida_bytes.get_cmt(ea, True)
            if flags != "":
                outfile.write("CCu base64:" + base64.b64encode(flags.encode(
                    encoding='UTF-8')).decode("utf-8") + " @ " + str(ea) + "\n")
        except Exception as e:
            try:
                flags = api.ida_bytes.get_cmt(ea, False)
                outfile.write("CCu base64:" + base64.b64encode(flags.encode(
                    encoding='UTF-8')).decode("utf-8") + " @ " + str(ea) + "\n")
            except:
                pass


def idb2r2_functions(api):
    ''' Convert all functions from the IDB
    '''

    for ea in api.idautils.Functions():
        outfile.write(
            "af " + api.idc.GetFunctionName(ea).replace("@", "_") + " @ " + str(ea) + "\n")


def idb_parse(args):
    global outfile
    with idb.from_file(args.idb_file) as db:
        api = idb.IDAPython(db)
        # Compatability check for those who install python-idb from pip
        try:
            baddr = hex(api.ida_nalt.get_imagebase())
        except:
            baddr = "[base address]"
        outfile = open(args.out_file, 'w')

        print("[+] Starting convertion from '%s' to '%s'" %
                (args.idb_file, args.out_file))

        if args.is_functions:
            idb2r2_functions(api)

        if args.is_comments:
            segs = idb.analysis.Segments(db).segments
            for segment in segs.values():
                idb2r2_comments(api, segment.startEA)

    print("[+] Convertion done.\n")
    print("[!] Execute: r2 -i %s -B %s [program]\n" %
            (args.out_file, baddr))

#
# End of IDB Parsing
###


# -------------------------------------------------------------------


###
# IDC Parsing
#

class Func(object):
# FIXME: parse ftype into params and values
	def __init__(self, name="unknown", params=[], values=[], address=0, size=0, ftype=""):
		self.name = name
		self.params = params
		self.values = values
		self.address = address
		self.size = size
		self.ftype = ftype

class Llabel(object):
	def __init__(self, name="unknown", address=0):
		self.name = name
		self.address = address

class Comm(object):
	def __init__(self, text="", address=0):
		self.text = text
		self.address = address

class Enum(object):
	def __init__(self, name="unknown", members=[]):
		self.name = name
		self.members = members

class Struct(object):
	def __init__(self, name="unknown", members=[]):
		self.name = name
		self.members = members

class Union(object):
	def __init__(self, name="unknown", members=[]):
		self.name = name
		self.members = members

class Type(object):
	def __init__(self, name="unknown"):
		self.name = name
		self.members = members

# ----------------------------------------------------------------------

functions = []
llabels = []
comments = []
structs = []
enums = []
types = []

def idc_functions_parse(idc):

	# MakeFunction (0XF3C99,0XF3CA8);
	mkfun_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*MakeFunction[ \t]*\(
		(?P<fstart>0[xX][\dA-Fa-f]{1,8})	# Function start
		[ \t]*\,[ \t]*
		(?P<fend>0[xX][\dA-Fa-f]{1,8})		# Function end
		[ \t]*\);[ \t]*$
		""", re.VERBOSE)
	mkfun_group_name = dict([(v,k) for k,v in mkfun_re.groupindex.items()])
	mkfun = mkfun_re.finditer(idc)
	for match in mkfun :
		fun = Func()
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mkfun_group_name[group_index+1] == "fstart" :
					fun.address = int(group, 16)
				if mkfun_group_name[group_index+1] == "fend" :
					fun.size = int(group, 16) - fun.address

		functions.append(fun)

	# SetFunctionFlags (0XF3C99, 0x400);
	mkfunflags_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*SetFunctionFlags[ \t*]\(
		(?P<fstart>0[xX][\dA-Fa-f]{1,8})	# Function start
		[ \t]*\,[ \t]*
		(?P<flags>0[xX][\dA-Fa-f]{1,8})		# Flags
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)
	mkfunflags_group_name = dict([(v,k) for k,v in mkfunflags_re.groupindex.items()])
	mkfunflags = mkfunflags_re.finditer(idc)
	for match in mkfunflags :
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mkfunflags_group_name[group_index+1] == "fstart" :
					addr = int(group, 16)
				if mkfunflags_group_name[group_index+1] == "flags" :
					for fun in functions :
						if fun.address == addr :
							pass # TODO: parse flags


	# MakeFrame (0XF3C99, 0, 0, 0);
	# MakeName (0XF3C99, "SIO_port_setup_S");
	mkname_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*MakeName[ \t]*\(
		(?P<fstart>0[xX][\dA-Fa-f]{1,8})	# Function start
		[ \t]*\,[ \t]*
		"(?P<fname>.*)"						# Function name
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)
	mkname_group_name = dict([(v,k) for k,v in mkname_re.groupindex.items()])
	mkname = mkname_re.finditer(idc)
	for match in mkname :
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mkname_group_name[group_index+1] == "fstart" :
					addr = int(group, 16)
				if mkname_group_name[group_index+1] == "fname" :
					for fun in functions :
						if fun.address == addr :
							fun.name = group

	# SetType (0XFFF72, "__int32 __cdecl PCI_ByteWrite_SL(__int32 address, __int32 value)");
	mkftype_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*SetType[ \t]*\(
		(?P<fstart>0[xX][\dA-Fa-f]{1,8})	# Function start
		[ \t]*\,[ \t]*
		"(?P<ftype>.*)"						# Function type
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)
	mkftype_group_name = dict([(v,k) for k,v in mkftype_re.groupindex.items()])
	mkftype = mkftype_re.finditer(idc)
	for match in mkftype :
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mkftype_group_name[group_index+1] == "fstart" :
					addr = int(group, 16)
				if mkftype_group_name[group_index+1] == "ftype" :
					for fun in functions :
						if fun.address == addr :
							fun.ftype = group

	# MakeNameEx (0xF3CA0, "return", SN_LOCAL);
	mklocal_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*MakeNameEx[ \t]*\(
		(?P<laddr>0[xX][\dA-Fa-f]{1,8})		# Local label address
		[ \t]*\,[ \t]*
		"(?P<lname>.*)"						# Local label name
		[ \t]*\,[ \t]*SN_LOCAL
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)
	mklocal_group_name = dict([(v,k) for k,v in mklocal_re.groupindex.items()])
	mklocal = mklocal_re.finditer(idc)
	for match in mklocal :
		lab = Llabel()
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mklocal_group_name[group_index+1] == "laddr" :
					lab.address = int(group, 16)
				if mklocal_group_name[group_index+1] == "lname" :
					lab.name = group
		llabels.append(lab)

# ----------------------------------------------------------------------

def idc_enums_parse(idc):
	pass

# ----------------------------------------------------------------------

def idc_structs_parse(idc):
	# id = AddStrucEx (-1, "struct_MTRR", 0);
	mkstruct_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*id[ \t]*=[ \t]*AddStrucEx[ \t]*\(
		[ \t]*-1[ \t]*,[ \t]*
		"(?P<sname>.*)"						# Structure name
		[ \t]*\,[ \t]*0
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)
	mkstruct_group_name = dict([(v,k) for k,v in mkstruct_re.groupindex.items()])
	mkstruct = mkstruct_re.finditer(idc)
	for match in mkstruct :
		s = Struct()
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mkstruct_group_name[group_index+1] == "sname" :
					s.name = group
		structs.append(s)

	# Case 1: not nested structures
	# =============================
	# id = GetStrucIdByName ("struct_header");
	# mid = AddStructMember(id,"BCPNV", 0, 0x5000c500, 0, 7);
	# mid = AddStructMember(id,"_", 0X7, 0x00500, -1, 1);
	# mid = AddStructMember(id, "BCPNV_size",0X8, 0x004500, -1, 1);
	mkstruct_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*id[ \t]*=[ \t]*GetStrucIdByName[ \t]*\(
		[ \t]*-1[ \t]*,[ \t]*
		"(?P<sname>.*)"						# Structure name
		[ \t]*\,[ \t]*0
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)

# ----------------------------------------------------------------------

def idc_comments_parse(idc):
	# MakeComm (0XFED3D, "PCI class 0x600 - Host/PCI bridge");
	mkcomm_re = re.compile("""
		(?m)								# Multiline
		^[ \t]*MakeComm[ \t]*\(
		(?P<caddr>0[xX][\dA-Fa-f]{1,8})		# Comment address
		[ \t]*\,[ \t]*
		"(?P<ctext>.*)"						# Comment
		[ \t]*\);[ \t]*$
	""", re.VERBOSE)
	mkcomm_group_name = dict([(v,k) for k,v in mkcomm_re.groupindex.items()])
	mkcomm = mkcomm_re.finditer(idc)
	for match in mkcomm :
		for group_index,group in enumerate(match.groups()) :
			if group :
				if mkcomm_group_name[group_index+1] == "caddr" :
					address = int(group, 16)
				if mkcomm_group_name[group_index+1] == "ctext" :
					com_multi = group.split('\\n')
					for a in com_multi :
						com = Comm()
						com.address = address
						com.text = a
						comments.append(com)

# ----------------------------------------------------------------------

#	print("af+ 0x%08lx %d %s" % (func.address, func.size, func.name))

def idc_generate_r2(out_file):
	global outfile
	outfile = open(out_file, 'w')

	for f in functions :
		if f.name != "unknown" :
			outfile.write("af+ {0} {1} {2}\n".format(hex(f.address), f.size, f.name))
			outfile.write("\"CCa {0} {1}\"\n".format(hex(f.address), f.ftype))

	for l in llabels :
		if l.name != "unknown" :
			for f in functions :
				if (l.address > f.address) and (l.address < (f.address + f.size)) :
					outfile.write("f. {0} @ {1}\n".format(l.name, hex(l.address)))

	for c in comments :
		if c.text != "" :
			outfile.write("\"CCa {0} {1}\"\n".format(c.address, c.text))
    
	outfile.seek(0,2)
	if outfile.tell() == 0:
		print("[-] Found nothing to convert :-(")
		exit()


# ----------------------------------------------------------------------

def idc_parse(args):
	print("[+] Starting convertion from '%s' to '%s'" %
		(args.idc_file, args.out_file))
	idc_file = open(args.idc_file, "r")
	idc = idc_file.read()
	idc_enums_parse(idc)
	idc_structs_parse(idc)
	if args.is_functions:
		idc_functions_parse(idc)
	if args.is_comments:
		idc_comments_parse(idc)
	idc_generate_r2(args.out_file)
	print("[+] Convertion done.\n")
	print("[!] Execute: r2 -i %s [program]\n" %
		(args.out_file))

#
# End of IDC Parsing
###

# ----------------------------------------------------------------------

def main():
    ''' Gets arguments from the user. Perform convertion of the chosen data from the IDB into a radare2 initialization script
    '''
    args = get_args()

    if args.idb_file:
        idb_parse(args)
    elif args.idc_file:
        idc_parse(args)



if __name__ == "__main__":
    main()
