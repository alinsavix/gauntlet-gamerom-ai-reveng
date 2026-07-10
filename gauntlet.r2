# - 4 fd: 6 +0x00000000 0x00038000 - 0x0003ffff rwx
# * 3 fd: 5 +0x00000000 0x00000000 - 0x0000ffff rwx
# - 2 fd: 4 +0x00000000 0x00000000 - 0x0001ffff r--
# - 1 fd: 3 +0x00000000 0x00000000 - 0x0001ffff r--
# r2 rdb project file
# Merged 2026-07-09: base annotations (ex gauntlet.r2.bak) + database flags
# + analysis-session updates (ex gauntlet_updates.r2) are embedded below.
#
# NOTE: this project file does not set up memory maps. For correct addresses
# open the ROMs mapped like this before (or instead of) r2 -i:
#   r2 -n row9.bin   then:  o row10.bin 0x38000 r-x ; o row76.bin 0x40000 r-x
#   e asm.arch=m68k ; e asm.cpu=68010 ; e asm.bits=32 ; . gauntlet.r2
# eval
'e anal.arch = m68k
'e anal.autoname = false
'e anal.bb.maxsize = 512K
'e anal.brokenrefs = false
'e anal.calls = false
'e anal.cc = 
'e anal.cs = 0
'e anal.cxxabi = itanium
'e anal.datarefs = false
'e anal.delay = true
'e anal.depth = 128
'e anal.emu = true
'e anal.emumem = false
'e anal.esil = false
'e anal.fcnalign = 0
'e anal.fixed.arch = false
'e anal.fixed.bits = false
'e anal.fixed.gp = true
'e anal.fixed.thumb = true
'e anal.flagends = true
'e anal.from = 0xffffffffffffffff
'e anal.gp = 0
'e anal.graph_depth = 256
'e anal.hasnext = false
'e anal.hpskip = false
'e anal.icods = true
'e anal.ignbithints = false
'e anal.imports = true
'e anal.in = bin.ormaps.x
'e anal.jmp.above = true
'e anal.jmp.cref = false
'e anal.jmp.indir = false
'e anal.jmp.mid = true
'e anal.jmp.ref = true
'e anal.jmp.retpoline = true
'e anal.jmp.tailcall = true
'e anal.jmp.tailcall.delta = 0
'e anal.jmp.tbl = true
'e anal.limits = false
'e anal.loads = false
'e anal.mask = false
'e anal.nonull = 0
'e anal.nopskip = false
'e anal.noret = true
'e anal.noret.refs = false
'e anal.norevisit = false
'e anal.onchange = false
'e anal.prefix.default = fcn
'e anal.prefix.dynamic = false
'e anal.prefix.marker = pfx.fcn.
'e anal.prefix.radius = 0x00001000
'e anal.prelude = 
'e anal.ptrdepth = 3
'e anal.pushret = false
'e anal.recont = false
'e anal.refstr = false
'e anal.roregs = gp,zero
'e anal.sleep = 0
'e anal.slow = true
'e anal.strings = true
'e anal.symsort = 0
'e anal.syscc = 
'e anal.timeout = 0
'e anal.to = 0xffffffffffffffff
'e anal.trycatch = false
'e anal.types.constraint = false
'e anal.types.plugin = 
'e anal.types.rollback = false
'e anal.types.spec = gcc
'e anal.types.verbose = false
'e anal.vars = true
'e anal.vars.newstack = false
'e anal.vars.stackname = false
'e anal.verbose = false
'e anal.vinfun = false
'e anal.vinfunrange = false
'e arch.bits = 0x00004020
'e arch.codealign = 2
'e arch.decoder = null
'e arch.endian = little
'e arch.platform = 
'e asm.abi = 
'e asm.addr = true
'e asm.addr.base10 = false
'e asm.addr.base36 = false
'e asm.addr.focus = false
'e asm.addr.relto = 
'e asm.addr.segment = false
'e asm.addr.segment.bits = 4
'e asm.anal = false
'e asm.anos = true
'e asm.arch = m68k
'e asm.assembler = 
'e asm.bbmiddle = true
'e asm.bits = 32
'e asm.bytes = false
'e asm.bytes.align = false
'e asm.bytes.asbits = false
'e asm.bytes.ascii = false
'e asm.bytes.ascmt = false
'e asm.bytes.opcolor = false
'e asm.bytes.right = false
'e asm.bytes.space = false
'e asm.capitalize = false
'e asm.cmt.calls = true
'e asm.cmt.col = 71
'e asm.cmt.esil = false
'e asm.cmt.flgrefs = true
'e asm.cmt.fold = false
'e asm.cmt.off = nodup
'e asm.cmt.patch = false
'e asm.cmt.pseudo = false
'e asm.cmt.refs = false
'e asm.cmt.right = false
'e asm.cmt.strings = true
'e asm.cmt.token = ;
'e asm.cmt.user = false
'e asm.cmt.wrap = true
'e asm.comments = true
'e asm.cpu = 68010
'e asm.cycles = false
'e asm.cyclespace = false
'e asm.decode = false
'e asm.demangle = true
'e asm.describe = false
'e asm.dwarf = true
'e asm.dwarf.abspath = false
'e asm.dwarf.file = true
'e asm.emu = true
'e asm.esil = false
'e asm.family = false
'e asm.fcnsig = true
'e asm.flags = true
'e asm.flags.inbytes = false
'e asm.flags.inline = false
'e asm.flags.inoffset = false
'e asm.flags.limit = 0
'e asm.flags.maxname = 0
'e asm.flags.middle = 2
'e asm.flags.offset = false
'e asm.flags.prefix = true
'e asm.flags.real = false
'e asm.flags.right = false
'e asm.functions = true
'e asm.highlight = 
'e asm.hint.call = true
'e asm.hint.call.indirect = true
'e asm.hint.cdiv = false
'e asm.hint.emu = false
'e asm.hint.imm = false
'e asm.hint.jmp = false
'e asm.hint.lea = false
'e asm.hint.pos = 1
'e asm.hints = true
'e asm.imm.base = 0
'e asm.imm.str = true
'e asm.imm.trim = false
'e asm.indent = false
'e asm.indentspace = 2
'e asm.instr = true
'e asm.invhex = false
'e asm.lbytes = true
'e asm.lines = false
'e asm.lines.bb = false
'e asm.lines.call = false
'e asm.lines.fcn = false
'e asm.lines.jmp = true
'e asm.lines.limit = 0x00004000
'e asm.lines.maxref = 0
'e asm.lines.out = true
'e asm.lines.ret = false
'e asm.lines.right = false
'e asm.lines.split = false
'e asm.lines.wide = false
'e asm.lines.width = 7
'e asm.marks = true
'e asm.meta = true
'e asm.midcursor = false
'e asm.middle = false
'e asm.nbytes = 6
'e asm.nodup = false
'e asm.noisy = true
'e asm.optype = false
'e asm.os = darwin
'e asm.parser = m68k
'e asm.payloads = false
'e asm.pseudo = false
'e asm.pseudo.linear = false
'e asm.refptr = true
'e asm.section = false
'e asm.section.col = 20
'e asm.section.name = true
'e asm.section.perm = false
'e asm.size = false
'e asm.slow = true
'e asm.spp = false
'e asm.stackptr = false
'e asm.strip = 
'e asm.sub.jmp = true
'e asm.sub.names = true
'e asm.sub.reg = false
'e asm.sub.rel = true
'e asm.sub.section = false
'e asm.sub.tail = false
'e asm.sub.var = true
'e asm.sub.varmin = 256
'e asm.sub.varonly = true
'e asm.symbol = false
'e asm.symbol.col = 40
'e asm.syntax = intel
'e asm.tabs = 0
'e asm.tabs.off = 0
'e asm.tabs.once = false
'e asm.trace = false
'e asm.trace.color = true
'e asm.trace.space = false
'e asm.trace.stats = true
'e asm.types = 1
'e asm.ucase = false
'e asm.var = true
'e asm.var.access = false
'e asm.var.summary = 4
'e asm.xrefs = true
'e asm.xrefs.code = true
'e asm.xrefs.fold = 5
'e asm.xrefs.max = 20
'e bin.aslr = false
'e bin.at = false
'e bin.baddr = 0x00038000
'e bin.cache = true
'e bin.classes = true
'e bin.dbginfo = true
'e bin.demangle = true
'e bin.demangle.pfxlib = false
'e bin.demangle.trylib = false
'e bin.demangle.usecmd = false
'e bin.filter = true
'e bin.force = 
'e bin.hashlimit = 10M
'e bin.lang = 
'e bin.libs = false
'e bin.limit = 0
'e bin.maxsymlen = 0
'e bin.prefix = 
'e bin.relocs = true
'e bin.relocs.apply = true
'e bin.str.align = 0
'e bin.str.debase64 = false
'e bin.str.enc = guess
'e bin.str.filter = 
'e bin.str.max = 0
'e bin.str.maxbuf = 0x00a00000
'e bin.str.min = 0
'e bin.str.nofp = false
'e bin.str.purge = 
'e bin.str.raw = false
'e bin.str.real = false
'e bin.strings = true
'e bin.types = true
'e bin.useldr = true
'e bin.usextr = true
'e bin.verbose = false
'e cfg.autoflagspace = false
'e cfg.bigendian = false
'e cfg.charset = 
'e cfg.codevar = 
'e cfg.corelog = false
'e cfg.cpuaffinity = 0
'e cfg.debug = false
'e cfg.editor = code --wait
'e cfg.float = ieee754
'e cfg.fortunes = true
'e cfg.fortunes.clippy = false
'e cfg.fortunes.tts = false
'e cfg.fortunes.type = fun,tips
'e cfg.json.num = none
'e cfg.json.str = none
'e cfg.plugins = true
'e cfg.prefixdump = dump
'e cfg.r2wars = false
'e cfg.regnums = false
'e cfg.sandbox = false
'e cfg.sandbox.grain = all
'e cfg.table.format = 
'e cfg.table.maxcol = 0
'e cfg.table.wrap = false
'e cfg.taskmode = thread
'e cfg.user = jaygrizzard
'e cfg.wseek = false
'e cmd.bbgraph = 
'e cmd.bp = 
'e cmd.cprompt = 
'e cmd.depth = 10
'e cmd.esil.intr = 
'e cmd.esil.ioer = 
'e cmd.esil.mdev = 
'e cmd.esil.pin = 
'e cmd.esil.step = 
'e cmd.esil.stepout = 
'e cmd.esil.todo = 
'e cmd.esil.trap = 
'e cmd.exit = 
'e cmd.fcn.delete = 
'e cmd.fcn.new = 
'e cmd.fcn.rename = 
'e cmd.gprompt = 
'e cmd.hexcursor = 
'e cmd.hit = 
'e cmd.hitinfo = 1
'e cmd.load = 
'e cmd.log = 
'e cmd.onsyscall = 
'e cmd.open = 
'e cmd.pdc = 
'e cmd.prompt = 
'e cmd.repeat = false
'e cmd.stack = 
'e cmd.step = 
'e cmd.times = 
'e cmd.undo = true
'e cmd.usr1 = 
'e cmd.usr2 = 
'e cmd.visual = 
'e cmd.vprompt = 
'e cmd.vprompt2 = 
'e dbg.aftersyscall = true
'e dbg.args = 
'e dbg.backend = native
'e dbg.bep = loader
'e dbg.bpforuntil = true
'e dbg.bpinmaps = true
'e dbg.bpsize = 4
'e dbg.bpsysign = false
'e dbg.btalgo = fuzzy
'e dbg.btdepth = 128
'e dbg.clone = false
'e dbg.consbreak = false
'e dbg.exe.path = 
'e dbg.execs = false
'e dbg.exitkills = true
'e dbg.follow = 32
'e dbg.follow.child = false
'e dbg.forks = false
'e dbg.funcarg = false
'e dbg.gdb.page_size = 0x00001000
'e dbg.gdb.retries = 10
'e dbg.glibc.demangle = false
'e dbg.glibc.fc_offset = 328
'e dbg.glibc.ma_offset = 0x001bb000
'e dbg.glibc.main_arena = 0
'e dbg.glibc.path = 
'e dbg.glibc.tcache = false
'e dbg.glibc.version = 
'e dbg.hwbp = false
'e dbg.libs = 
'e dbg.linkurl = https://debuginfod.debian.net
'e dbg.malloc = macos
'e dbg.maxsnapsize = 32M
'e dbg.profile = 
'e dbg.rebase = true
'e dbg.skipover = false
'e dbg.slow = false
'e dbg.status = false
'e dbg.swstep = false
'e dbg.threads = false
'e dbg.trace = false
'e dbg.trace.continue = true
'e dbg.trace.eval = true
'e dbg.trace.inrange = false
'e dbg.trace.libs = true
'e dbg.trace.tag = 0
'e dbg.unlibs = 
'e dbg.verbose = false
'e dbg.wrap = false
'e diff.bare = false
'e diff.from = 0
'e diff.levenstein = false
'e diff.sort = addr
'e diff.to = 0
'e emu.bb = false
'e emu.lazy = false
'e emu.maxsize = 128M
'e emu.pre = false
'e emu.skip = ds
'e emu.ssa = false
'e emu.stack = false
'e emu.str = true
'e emu.str.flag = true
'e emu.str.inv = true
'e emu.str.lea = true
'e emu.str.off = false
'e emu.write = false
'e esil.addr.size = 64
'e esil.breakoninvalid = false
'e esil.dfg.mapinfo = false
'e esil.dfg.maps = false
'e esil.exectrap = false
'e esil.fillstack = 
'e esil.gotolimit = 0x00001000
'e esil.iotrap = true
'e esil.maxsteps = 0
'e esil.mdev.range = 
'e esil.nonull = false
'e esil.prestep = true
'e esil.romem = false
'e esil.stack.addr = 0x00100000
'e esil.stack.depth = 256
'e esil.stack.pattern = 0
'e esil.stack.size = 0x000f0000
'e esil.stats = false
'e esil.timeout = 0
'e esil.traprevert = false
'e esil.verbose = 0
'e file.info = true
'e file.loadalign = 0x00000400
'e file.type = 
'e fs.cwd = /
'e fs.view = normal
'e graph.addr = false
'e graph.aeab = false
'e graph.bb.maxwidth = 0
'e graph.body = true
'e graph.bubble = false
'e graph.bytes = false
'e graph.cmtright = false
'e graph.comments = true
'e graph.dotted = false
'e graph.dummy = true
'e graph.edges = 2
'e graph.few = false
'e graph.font = Courier
'e graph.from = 0xffffffffffffffff
'e graph.gv.current = false
'e graph.gv.edge = 
'e graph.gv.format = gif
'e graph.gv.graph = 
'e graph.gv.node = 
'e graph.gv.spline = 
'e graph.hints = true
'e graph.invscroll = false
'e graph.json.usenames = true
'e graph.layout = 0
'e graph.linemode = 1
'e graph.mini = false
'e graph.nodejmps = true
'e graph.ntitles = true
'e graph.refs = false
'e graph.scroll = 5
'e graph.title = 
'e graph.to = 0xffffffffffffffff
'e graph.trace = false
'e graph.zoom = 0
'e hex.addr = true
'e hex.align = false
'e hex.ascii = true
'e hex.bytes = true
'e hex.cols = 16
'e hex.comments = true
'e hex.compact = false
'e hex.depth = 5
'e hex.flagsz = 0
'e hex.hdroff = true
'e hex.header = true
'e hex.onechar = false
'e hex.pairs = true
'e hex.section = false
'e hex.stride = 0
'e hex.style = false
'e http.allow = 
'e http.auth = false
'e http.authfile = 
'e http.authtok = r2admin:r2admin
'e http.basepath = /
'e http.bind = localhost
'e http.browser = 
'e http.channel = false
'e http.colon = false
'e http.cors = false
'e http.dietime = 0
'e http.dirlist = false
'e http.homeroot = /Users/jaygrizzard/.local/share/radare2/www
'e http.index = index.html
'e http.log = true
'e http.logfile = 
'e http.maxport = 9999
'e http.maxsize = 0
'e http.port = 9090
'e http.referer = 
'e http.root = /opt/homebrew/Cellar/radare2/6.0.8/share/radare2/6.0.8/www
'e http.sandbox = true
'e http.sync = 
'e http.timeout = 3
'e http.ui = m
'e http.upget = false
'e http.upload = false
'e http.uproot = /var/folders/l1/6n5xlffd1qx07_mf6_v89nq40000gn/T/
'e http.uri = 
'e http.verbose = false
'e hud.path = 
'e io.0xff = 255
'e io.autofd = true
'e io.basemap = false
'e io.cache = true
'e io.cache.auto = false
'e io.cache.nodup = false
'e io.cache.read = true
'e io.cache.write = true
'e io.exec = true
'e io.ff = true
'e io.mapinc = 0x10000000
'e io.mask = 0
'e io.overlay = true
'e io.pava = false
'e io.pcache = false
'e io.pcache.read = false
'e io.pcache.write = false
'e io.unalloc = false
'e io.unalloc.ch = .
'e io.va = true
'e io.voidwrites = true
'e key.S = 
'e key.f1 = 
'e key.f10 = 
'e key.f11 = 
'e key.f12 = 
'e key.f2 = 
'e key.f3 = 
'e key.f4 = 
'e key.f5 = 
'e key.f6 = 
'e key.f7 = 
'e key.f8 = 
'e key.f9 = 
'e key.s = 
'e lines.abs = false
'e lines.from = 0
'e lines.to = $s
'e log.color = false
'e log.cons = false
'e log.file = 
'e log.filter = 
'e log.level = 4
'e log.origin = false
'e log.quiet = false
'e log.source = false
'e log.traplevel = 0
'e log.ts = false
'e pdb.autoload = 0
'e pdb.extract = 1
'e pdb.server = https://msdl.microsoft.com/download/symbols
'e pdb.symstore = /Users/jaygrizzard/.local/share/radare2/pdb
'e pdb.useragent = microsoft-symbol-server/6.11.0001.402
'e prj.alwasyprompt = false
'e prj.files = false
'e prj.gpg = false
'e prj.history = false
'e prj.name = 
'e prj.sandbox = false
'e prj.vc = true
'e prj.vc.message = 
'e prj.vc.type = git
'e prj.zip = false
'e rap.loop = true
'e rop.comments = false
'e rop.conditional = false
'e rop.db = true
'e rop.len = 5
'e rop.sdb = false
'e rop.subchains = false
'e scr.analbar = false
'e scr.bgfill = false
'e scr.breaklines = false
'e scr.breakword = 
'e scr.clippy = clippy
'e scr.color = 0
'e scr.color.args = true
'e scr.color.bytes = true
'e scr.color.grep = false
'e scr.color.ophex = false
'e scr.color.ops = true
'e scr.color.pipe = false
'e scr.color.regs = false
'e scr.cols = 0
'e scr.cols.fix = 0
'e scr.confirmquit = false
'e scr.css = false
'e scr.css.prefix = 
'e scr.cursor = false
'e scr.cursor.limit = true
'e scr.demo = false
'e scr.dumpcols = false
'e scr.echo = false
'e scr.feedback = 1
'e scr.fgets = false
'e scr.flush = true
'e scr.fps = false
'e scr.gadgets = true
'e scr.highlight = 
'e scr.highlight.grep = false
'e scr.hist.block = true
'e scr.hist.filter = true
'e scr.hist.save = true
'e scr.hist.size = 256
'e scr.html = false
'e scr.interactive = false
'e scr.last = true
'e scr.layout = 
'e scr.limit = 0x00004180
'e scr.linesleep = 0
'e scr.loopnl = false
'e scr.maxpage = 0x00019000
'e scr.maxtab = 0x00001000
'e scr.nkey = flag
'e scr.notch = 0
'e scr.null = false
'e scr.pager = 
'e scr.pagesize = 1
'e scr.panelborder = false
'e scr.progressbar = false
'e scr.prompt = false
'e scr.prompt.code = false
'e scr.prompt.file = false
'e scr.prompt.flag = false
'e scr.prompt.format = 
'e scr.prompt.mode = false
'e scr.prompt.popup = false
'e scr.prompt.prj = false
'e scr.prompt.sect = false
'e scr.prompt.tabhelp = true
'e scr.prompt.vi = false
'e scr.rainbow = false
'e scr.rainbow.regs = false
'e scr.randpal = false
'e scr.responsive = false
'e scr.rows = 0
'e scr.rows.fix = 0
'e scr.scrollbar = 0
'e scr.slow = true
'e scr.square = true
'e scr.strconv = asciiesc
'e scr.tee = 
'e scr.theme = default
'e scr.timeout = 0
'e scr.tts = false
'e scr.utf8 = false
'e scr.utf8.curvy = false
'e scr.vprompt.format = 
'e scr.vtmode = 0
'e scr.wheel = true
'e scr.wheel.nkey = false
'e scr.wheel.speed = 4
'e scr.wideoff = false
'e search.align = 0
'e search.badpages = true
'e search.chunk = 0
'e search.contiguous = true
'e search.distance = 0
'e search.esilcombo = 8
'e search.flags = true
'e search.from = 0xffffffffffffffff
'e search.in = io.maps
'e search.kwidx = 0
'e search.maxhits = 0
'e search.named = false
'e search.overlap = false
'e search.prefix = hit
'e search.show = true
'e search.to = 0xffffffffffffffff
'e search.verbose = false
'e stack.annotated = false
'e stack.bytes = true
'e stack.delta = 0
'e stack.reg = SP
'e stack.size = 64
'e str.escbslash = false
'e time.fmt = %Y-%m-%d %H:%M:%S %u
'e time.zone = 0
'e zign.autoload = false
'e zign.bytes = true
'e zign.diff.bthresh = 1.0
'e zign.diff.gthresh = 1.0
'e zign.dups = false
'e zign.graph = true
'e zign.hash = true
'e zign.mangled = false
'e zign.maxsz = 500
'e zign.mincc = 10
'e zign.minsz = 16
'e zign.offset = false
'e zign.prefix = sign
'e zign.refs = true
'e zign.threshold = 0.0
'e zign.types = true
'e zoom.byte = h
'e zoom.from = 0
'e zoom.in = io.map
'e zoom.maxsz = 512
'e zoom.to = 0
'e scr.pipecolor = false

o "/Users/jaygrizzard/git/claudetest3/row76.bin" 0xffffffffffffffff r-x
o "/Users/jaygrizzard/git/claudetest3/row76.bin" 0x00000000 r-x
o "/Users/jaygrizzard/git/claudetest3/row9.bin" 0xffffffffffffffff rwx
o "/Users/jaygrizzard/git/claudetest3/row10.bin" 0x00038000 rwx
omu 3 0x00000000 0x00020000 0x00000000 r--
omu 4 0x00000000 0x00020000 0x00000000 r--
omu 5 0x00000000 0x00010000 0x00000000 rwx
omu 6 0x00038000 0x00008000 0x00000000 rwx
o=6
tcc d0 m68k (stack_rev);
tcc a0 reg (a0, a1, a2, a3);
# functions
af+ 0x0300 exception_handler
af+ 0x0314 irq1_handler
af+ 0x0326 irq2_handler
af+ 0x0338 irq3_handler
af+ 0x034a irq4_vblank_handler
af+ 0x036c irq6_handler
af+ 0x05e2 reset_entry
af+ 0x03a0 normal_boot
af+ 0x061e selftest_boot
af+ 0x070c main_init_cont
af+ 0x0a2c mem_test_thorough
af+ 0x0a6a mem_test_quick
af+ 0x0c52 error_display_string
af+ 0x0c98 error_display_ram
af+ 0x0cc0 rom_checksum_display
af+ 0x0e14 os_vblank_mode_entry
af+ 0x0e5e os_vblank_handler
af+ 0x129a os_main_loop
af+ 0x2918 format_number
af+ 0x2a5e format_hex
af+ 0x2abe format_decimal
af+ 0x2e36 display_text
af+ 0x2f04 draw_string
af+ 0x2eb4 display_decimal_value
af+ 0x2eea display_hex_value
af+ 0x3044 write_alpha_char
af+ 0x2ce4 calc_alpha_address
af+ 0x3522 init_alpha_display
af+ 0x3586 write_alpha_word
af+ 0x3162 start_scroll_text
af+ 0x3168 start_scroll_type1
af+ 0x316c start_scroll_type3
af+ 0x3156 start_scroll_type4
af+ 0x3122 start_scroll_updown
af+ 0x30f4 stop_text_effect
af+ 0x3130 init_scroll_system
af+ 0x2b3c process_text_effects
af+ 0x31d2 display_large_text
af+ 0x3346 display_large_char_styled
af+ 0x32bc display_large_char_at
af+ 0x32a0 display_large_char_raw
af+ 0x35b2 set_text_position
af+ 0x332a large_char_lookup
af+ 0x32da large_char_data
af+ 0x3310 large_char_render
af+ 0x359a wait_vblanks
af+ 0x4184 send_sound_command
af+ 0x41fa process_sound
af+ 0x42c8 read_sound_data
af+ 0x427a send_sound_immediate
af+ 0x42f8 reset_sound_cpu
af+ 0x41c8 disable_interrupts
af+ 0x41cc enable_interrupts
af+ 0x432e eeprom_process
af+ 0x44e8 eeprom_init
af+ 0x47a8 eeprom_request_write
af+ 0x4802 eeprom_check_busy
af+ 0x4822 eeprom_read_block
af+ 0x35c4 process_coins
af+ 0x3706 get_coin_multiplier
af+ 0x3740 calc_health_per_coin
af+ 0x37c2 check_and_deduct_coin
af+ 0x3804 check_credits
af+ 0x3860 read_eeprom_setting
af+ 0x38c0 read_game_config
af+ 0x39b0 read_high_score_entry
af+ 0x3a7e write_high_score_entry
af+ 0x3be8 get_eeprom_base
af+ 0x3cf6 write_eeprom_setting
af+ 0x3f68 read_eeprom_config
af+ 0x401a write_eeprom_config
af+ 0x4038 process_coin_stats
af+ 0x5454 run_self_test
af+ 0x58c6 display_attract_screen
af+ 0x1632 display_init_clear
af+ 0x17d4 display_init_text
af+ 0x0fca display_init_palette
af+ 0x1b20 display_attract_setup
af+ 0x21a0 eeprom_validate
fs functions
# registers
fs+registers
f d0 4 0x00000000
f d1 4 0x00000000
f d2 4 0x00000000
f d3 4 0x00000000
f d4 4 0x00000000
f d5 4 0x00000000
f d6 4 0x00000000
f d7 4 0x00000000
f a0 4 0x00000000
f a1 4 0x00000000
f a2 4 0x00000000
f a3 4 0x00000000
f a4 4 0x00000000
f a5 4 0x00000000
f a6 4 0x00000000
f a7 4 0x00000000
f fp0 4 0x00000000
f fp1 4 0x00000000
f fp2 4 0x00000000
f fp3 4 0x00000000
f fp4 4 0x00000000
f fp5 4 0x00000000
f fp6 4 0x00000000
f fp7 4 0x00000000
f pc 4 0x00000000
f sr 4 0x00000000
f ccr 4 0x00000000
f sfc 4 0x00000000
f dfc 4 0x00000000
f usp 4 0x00000000
f vbr 4 0x00000000
f cacr 4 0x00000000
f caar 4 0x00000000
f msp 4 0x00000000
f isp 4 0x00000000
f tc 4 0x00000000
f itt0 4 0x00000000
f itt1 4 0x00000000
f dtt0 4 0x00000000
f dtt1 4 0x00000000
f mmusr 4 0x00000000
f urp 4 0x00000000
f srp 4 0x00000000
f fpcr 4 0x00000000
f fpsr 4 0x00000000
f fpiar 4 0x00000000
fs-
aer d0 = 0x00000000
aer d1 = 0x00000000
aer d2 = 0x00000000
aer d3 = 0x00000000
aer d4 = 0x00000000
aer d5 = 0x00000000
aer d6 = 0x00000000
aer d7 = 0x00000000
aer a0 = 0x00000000
aer a1 = 0x00000000
aer a2 = 0x00000000
aer a3 = 0x00000000
aer a4 = 0x00000000
aer a5 = 0x00000000
aer a6 = 0x00000000
aer a7 = 0x00000000
aer fp0 = 0x00000000
aer fp1 = 0x00000000
aer fp2 = 0x00000000
aer fp3 = 0x00000000
aer fp4 = 0x00000000
aer fp5 = 0x00000000
aer fp6 = 0x00000000
aer fp7 = 0x00000000
aer pc = 0x00000000
aer sr = 0x00000000
aer ccr = 0x00000000
aer sfc = 0x00000000
aer dfc = 0x00000000
aer usp = 0x00000000
aer vbr = 0x00000000
aer cacr = 0x00000000
aer caar = 0x00000000
aer msp = 0x00000000
aer isp = 0x00000000
aer tc = 0x00000000
aer itt0 = 0x00000000
aer itt1 = 0x00000000
aer dtt0 = 0x00000000
aer dtt1 = 0x00000000
aer mmusr = 0x00000000
aer urp = 0x00000000
aer srp = 0x00000000
aer fpcr = 0x00000000
aer fpsr = 0x00000000
aer fpiar = 0x00000000
# flags
fs functions
'f exception_handler 1 0x00000300 
'f irq1_handler 1 0x00000314 
'f irq2_handler 1 0x00000326 
'f irq3_handler 1 0x00000338 
'f irq4_vblank_handler 1 0x0000034a 
'f irq6_handler 1 0x0000036c 
'f normal_boot 1 0x000003a0 
'f reset_entry 1 0x000005e2 
'f selftest_boot 1 0x0000061e 
'f main_init_cont 1 0x0000070c 
'f mem_test_thorough 1 0x00000a2c 
'f mem_test_quick 1 0x00000a6a 
'f error_display_string 1 0x00000c52 
'f error_display_ram 1 0x00000c98 
'f rom_checksum_display 1 0x00000cc0 
'f os_vblank_mode_entry 1 0x00000e14 
'f os_vblank_handler 1 0x00000e5e 
'f display_init_palette 1 0x00000fca 
'f os_main_loop 1 0x0000129a 
'f display_init_clear 1 0x00001632 
'f display_init_text 1 0x000017d4 
'f display_attract_setup 1 0x00001b20 
'f eeprom_validate 1 0x000021a0 
'f format_number 1 0x00002918 
'f format_hex 1 0x00002a5e 
'f format_decimal 1 0x00002abe 
'f process_text_effects 1 0x00002b3c 
'f calc_alpha_address 1 0x00002ce4 
'f display_text 1 0x00002e36 
'f display_decimal_value 1 0x00002eb4 
'f display_hex_value 1 0x00002eea 
'f draw_string 1 0x00002f04 
'f write_alpha_char 1 0x00003044 
'f stop_text_effect 1 0x000030f4 
'f start_scroll_updown 1 0x00003122 
'f init_scroll_system 1 0x00003130 
'f start_scroll_type4 1 0x00003156 
'f start_scroll_text 1 0x00003162 
'f start_scroll_type1 1 0x00003168 
'f start_scroll_type3 1 0x0000316c 
'f display_large_text 1 0x000031d2 
'f display_large_char_raw 1 0x000032a0 
'f display_large_char_at 1 0x000032bc 
'f large_char_data 1 0x000032da 
'f large_char_render 1 0x00003310 
'f large_char_lookup 1 0x0000332a 
'f display_large_char_styled 1 0x00003346 
'f init_alpha_display 1 0x00003522 
'f write_alpha_word 1 0x00003586 
'f wait_vblanks 1 0x0000359a 
'f set_text_position 1 0x000035b2 
'f process_coins 1 0x000035c4 
'f get_coin_multiplier 1 0x00003706 
'f calc_health_per_coin 1 0x00003740 
'f check_and_deduct_coin 1 0x000037c2 
'f check_credits 1 0x00003804 
'f read_eeprom_setting 1 0x00003860 
'f read_game_config 1 0x000038c0 
'f read_high_score_entry 1 0x000039b0 
'f write_high_score_entry 1 0x00003a7e 
'f get_eeprom_base 1 0x00003be8 
'f write_eeprom_setting 1 0x00003cf6 
'f read_eeprom_config 1 0x00003f68 
'f write_eeprom_config 1 0x0000401a 
'f process_coin_stats 1 0x00004038 
'f send_sound_command 1 0x00004184 
'f disable_interrupts 1 0x000041c8 
'f enable_interrupts 1 0x000041cc 
'f process_sound 1 0x000041fa 
'f send_sound_immediate 1 0x0000427a 
'f read_sound_data 1 0x000042c8 
'f reset_sound_cpu 1 0x000042f8 
'f eeprom_process 1 0x0000432e 
'f eeprom_init 1 0x000044e8 
'f eeprom_request_write 1 0x000047a8 
'f eeprom_check_busy 1 0x00004802 
'f eeprom_read_block 1 0x00004822 
'f run_self_test 1 0x00005454 
'f display_attract_screen 1 0x000058c6 
fs *
'f game.start 1 0x00040000 
'f game.vblank_handler 1 0x00040006 
'f game.irq1_handler 1 0x0004000c 
'f game.irq3_handler 1 0x00040012 
'f game.irq2_handler 1 0x00040018 
'f game.irq6_handler 1 0x0004001e 
'f game.exception_handler 1 0x00040024 
'f game.startup_hook2 1 0x0004002a 
'f game.playfield_init 1 0x00040030 
'f game.startup_hook1 1 0x00040036 
'f game.startup_hook3 1 0x0004003c 
'f game.vblank_hook 1 0x00040042 
'f game.attract_handler 1 0x00040048 
'f game.post_attract_hook 1 0x0004004e 
'f game.eeprom_config 1 0x00040054 
'f game.mob_fill_value 1 0x00040060 
'f game.pf_fill_value 1 0x00040062 
'f game.eeprom_start 1 0x0004006d 
'f game.difficulty_byte 1 0x0004006f 
'f game.screen_mode 1 0x00040070 
'f game.rom_type_flag 1 0x00040072 
'f game.button0_label_ptr 1 0x00040074 
'f game.button1_label_ptr 1 0x00040078 
'f game.joystick_label_ptr 1 0x0004007c 
'f game.checksum_table 1 0x00040080 
'f game_start 1 0x0004014c 
'f game_vblank 1 0x0004017e 
'f main_cycle_tport_and_ffield 1 0x00040528 
'f calc_score_per_coin 1 0x00040628 
'f input_debounce 1 0x00040644 
'f find_maze 1 0x00040c78 
'f monster_count_table 1 0x00040e46 
'f monsters_everything 1 0x00040e6a 
'f monster_find_and_shoot 1 0x00041750 
'f find_unused_shot 1 0x00041b16 
'f m2mainloop 1 0x00042a66 
'f coincheck 1 0x00042b6a 
'f main_sound_response 1 0x00042d0a 
'f sound_timeout_reset 1 0x00042dc8 
'f pick_character 1 0x00042df4 
'f maze_randomplace 1 0x00042e9a 
'f eeprom_periodic_write 1 0x000431ee 
'f game_init_settings 1 0x0004327a 
'f player_resetcounters 1 0x00043360 
'f player_resetall 1 0x0004341e 
'f get_random_maze_flags 1 0x000436cc 
'f maze_load_pickup_config 1 0x000436fe 
'f slapstic_cmd_bitwise 1 0x00043826 
'f maze_new_level_setup 1 0x000438ae 
'f maze_scan_objects 1 0x00043d8c 
'f maze_addrandompickups 1 0x00043f68 
'f game_new_setup 1 0x00044204 
'f main_attract 1 0x00044562 
'f fcn_449d4 1 0x000449d4 
'f maze_setupnew 1 0x00044ac2 
'f update_maze_player_count 1 0x00044c7e 
'f maze_show 1 0x0004526a 
'f maze_hide 1 0x0004529a 
'f setup_infopanel 1 0x000452d0 
'f main_score_display 1 0x000457c0 
'f player_it_set 1 0x00045866 
'f player_it_unset 1 0x0004590e 
'f player_inv_update 1 0x00045aca 
'f stridx 1 0x00045be8 
'f main_open_doors 1 0x00045c00 
'f maze_tile_write 1 0x00045e40 
'f maze_tile_write_at 1 0x0004631c 
'f main_handle_death 1 0x0004664c 
'f main_health_countdown 1 0x000466f6 
'f scroll_to_slot 1 0x00046c5e 
'f main_scroll_playfield 1 0x00046caa 
'f set_scroll_pos 1 0x00046f56 
'f main_handle_potions 1 0x00046fea 
'f main_score_update 1 0x0004715e 
'f main_handle_shots 1 0x000474f6 
'f tport_cycle_start 1 0x00047c0e 
'f handle_tport 1 0x00047cfe 
'f shot_impact_spawn 1 0x00047dae 
'f main_start_game 1 0x0004800c 
'f secret_check 1 0x000486fe 
'f speech_welcome 1 0x00048754 
'f player_lowhealth 1 0x000487ca 
'f player_coindrop 1 0x000488ca 
'f player_join2 1 0x00048a36 
'f player_join 1 0x00048bb6 
'f player_join_setup 1 0x00048bec 
'f traversable_check 1 0x00048f12 
'f main_move_monsters 1 0x00049034 
'f monster_create_shot 1 0x000490dc 
'f handle_generate 1 0x000492c0 
'f death_potion 1 0x00049446 
'f playfield_showscore 1 0x00049498 
'f monster_playerhit 1 0x000495a6 
'f death_damagetrack 1 0x00049a3c 
'f sound_player_hurt 1 0x00049a98 
'f highscore_check 1 0x00049d0e 
'f attract_highscores 1 0x0004a124 
'f main_move_players 1 0x0004a53a 
'f sound_speech_play 1 0x0004ad4e 
'f sound_play 1 0x0004ad76 
'f sound_init 1 0x0004adae 
'f main_update_sound 1 0x0004ae20 
'f shot_onscreen_check 1 0x0004aea0 
'f resolve_shot_hit 1 0x0004af50 
'f resolve_shot_hit_jumptbl 1 0x0004b336 
'f level_splash 1 0x0004be24 
'f maze_decode 1 0x0004c1bc 
'f dialog_first_encounter 1 0x0004c440 
'f dialog_clear_message 1 0x0004c70a 
'f player_give_item_with_message 1 0x0004c72a 
'f dialog_position_box 1 0x0004cb50 
'f main_msgbox_countdown 1 0x0004ccbc 
'f main_treasure_timer 1 0x0004d29e 
'f show_continue_screen 1 0x0004d476 
'f player_activecount 1 0x0004d900 
'f main_logo_updcolors 1 0x0004dcba 
'f main_start_thief 1 0x0004deb8 
'f thief_target_calc 1 0x0004dff6 
'f thief_exit 1 0x0004e122 
'f thief_setup 1 0x0004e432 
'f thief_timer_set 1 0x0004e4d8 
'f tport_find_id 1 0x0004e7c0 
'f thief_jumpjump_anim 1 0x0004e8dc 
'f thief_steal_effect 1 0x0004f912 
'f player_tport 1 0x00050224 
'f tport_player_flash 1 0x00050616 
'f tport_player_move 1 0x00050662 
'f tport_check_dest 1 0x00050ade 
'f calc_direction 1 0x000510fc 
'f player_tile_interact 1 0x000511ac 
'f player_add_score_with_mult 1 0x0005214c 
'f main_exit_move 1 0x0005287c 
'f exit_get_id 1 0x00052b06 
'f player_exit_sequence 1 0x00052b40 
'f maze_checknum 1 0x00052eca 
'f maze_forcefield_setup 1 0x00052f26 
'f wall_crumble 1 0x0005303a 
'f maze_objects_setup 1 0x00053398 
'f shot_reflect_calc 1 0x00053818 
'f dragon_shot_hit 1 0x00054112 
'f main_handle_dragon 1 0x00054454 
'f dragon_fire_setup 1 0x00054748 
'f dragon_player_proximity 1 0x000549ea 
'f secret_getname 1 0x00054ec6 
'f slapstic_cmd_bank0 1 0x00056e58 
'f slapstic_cmd_bank3 1 0x00056e6e 
'f slapstic_cmd_bankX 1 0x00056e84 
'f slapstic_verify 1 0x00056eaa 
'f dialog_tip_ptrs 1 0x0005815c 
'f dialog_tip_records 1 0x0005828c 
'f mazeobj_spawn_param_tbl 1 0x0005860c 
'f mazeobj_tier_base_tbl 1 0x0005864c 
'f mazeobj_spawn_pics_tbl 1 0x0005868c 
'f shot_damage_base_tbl 1 0x000596b6 
'f shot_damage_rand_tbl 1 0x000596c2 
'f monstshot_damage_tbl 1 0x000596ce 
'f speech_charname_tbl 1 0x000596f6 
'f maze_decomp_type_ptrs 1 0x00059b54 
'f floor_desc_base 1 0x0005bae0 
'f wall_desc_blocks 1 0x0005bbe0 
'f wall_desc_pattern6 1 0x0005d2f8 
'f wall_desc_destructible 1 0x0005d3d0 
'f dragon_head_hdelta 1 0x0005d438 
'f dragon_head_vdelta 1 0x0005d478 
'f dragon_fire_segment_tbl 1 0x0005d4b8 
'f dragon_head_pics 1 0x0005d528 
'f dragon_path_programs 1 0x0005d578 
'f playfield_palettes 1 0x0005d5c8 
'f playfield_palette_alt1 1 0x0005d7c8 
'f playfield_palette_alt2 1 0x0005d7e8 
'f aux_palettes 1 0x0005d808 
'f secretcode_text_recs 1 0x0005d9e8 
'f mob_create 1 0x0005dc58 
'f moblist_insert 1 0x0005dcbc 
'f moblist_replace 1 0x0005dd72 
'f moblist_remove 1 0x0005dda8 
'f moblist_remove_and_clear 1 0x0005ddda 
'f mob_update_slot 1 0x0005de0a 
'f mob_update_slot_cont 1 0x0005de44 
'f mob_place_tport_anim 1 0x0005df5a 
'f mob_place_shot 1 0x0005df68 
'f mob_place_anim 1 0x0005df72 
'f exit_create_player_anim 1 0x0005df80 
'f tport_create_splodey 1 0x0005df8e 
'f mob_place_explosion 1 0x0005df9c 
'f mob_unlink 1 0x0005e064 
'f mob_check_up 1 0x0005e10c 
'f mob_check_down 1 0x0005e1d8 
'f mob_check_left 1 0x0005e2a2 
'f mob_check_right 1 0x0005e35e 
'f main_walls_random_move 1 0x0005e41a 
'f pf_stamp_update 1 0x0005e536 
'f pos_onscreen 1 0x0005e584 
'f main_walls_cyclic_move 1 0x0005e62a 
'f maze_special_floor 1 0x0005e868 
'f pf_floor_draw_xy 1 0x0005e888 
'f pf_floor_update 1 0x0005e892 
'f maze_floor_decor 1 0x0005ea00 
'f pf_isblankfloor 1 0x0005ea2e 
'f pf_wall_draw_xy 1 0x0005eab8 
'f pf_wall_draw 1 0x0005eac2 
'f wall_pattern_offsets 1 0x0005edd4 
'f wall_random_desc_ptrs 1 0x0005edf4 
'f wall_conn_variant_tbl 1 0x0005ee24 
'f wall_conn_variant_tbl6 1 0x0005ef24 
'f maze_init_walls 1 0x0005f2c0 
'f pf_replace 1 0x0005f31e 
'f refresh_tile_visual 1 0x0005f5a0 
'f pf_isdoor 1 0x0005f77a 
'f maze_doors_setup 1 0x0005f7c0 
'f pf_door_update_surrounding_xy 1 0x0005f7f0 
'f pf_door_update_surrounding 1 0x0005f7fa 
'f pf_door_draw_xy 1 0x0005f876 
'f pf_door_draw 1 0x0005f880 
'f door_gfx_by_neighbors 1 0x0005f9ce 
'f door_gfx_type2 1 0x0005faca 
'f door_vpos_sub3 1 0x0005fbee 
'f door_vpos_add3 1 0x0005fc00 
'f getrandom_r 1 0x0005fc46 
'f getrandom 1 0x0005fc4e 
'f pf_isff 1 0x0005fc5e 
'f pf_palette_clear 1 0x0005fcce 
'f memclear 1 0x0005fd58 
'f memcpy 1 0x0005fd6a 
'f palette_fade_copy 1 0x0005fd80 
'f fcn.0005fdac 1 0x0005fdac 
'f supersorc_place 1 0x0005fde0 
'f hw.eeprom 1 0x00802001 
'f hw.player1_input 1 0x00803001 
'f hw.player2_input 1 0x00803003 
'f hw.player3_input 1 0x00803005 
'f hw.player4_input 1 0x00803007 
'f hw.vblank_selftest 1 0x00803009 
'f hw.sound_read 1 0x0080300f 
'f hw.watchdog 1 0x00803100 
'f hw.led1 1 0x00803121 
'f hw.led2 1 0x00803123 
'f hw.led3 1 0x00803125 
'f hw.led4 1 0x00803127 
'f hw.aux_latch 1 0x0080312f 
'f hw.sound_reset 1 0x0080312f 
'f hw.vblank_ack 1 0x00803140 
'f hw.eeprom_unlock 1 0x00803150 
'f hw.sound_write 1 0x00803171 
'f vram.playfield 1 0x00900000 
'f vram.mob_picture 1 0x00902000 
'f vram.mob_hpos 1 0x00902800 
'f vram.mob_vpos 1 0x00903000 
'f vram.mob_link 1 0x00903800 
'f ram.os_flag 1 0x00904000 
'f vram.spare 1 0x00904000 
'f ram.vblank_semaphore 1 0x00904002 
'f ram.levelnum_current 1 0x00904004 
'f ram.pf_vscroll_hi 1 0x00904006 
'f ram.pf_hscroll 1 0x00904008 
'f ram.pf_vscroll_lo 1 0x0090400a 
'f ram.timer_countdown 1 0x0090400c 
'f ram.sound_data_recv 1 0x0090400e 
'f ram.sound_data_flag 1 0x00904010 
'f ram.game_hook_flag 1 0x00904014 
'f ram.dragon_fire_cooldown 1 0x0090487c 
'f ram.dialog_once_flags 1 0x0090487e 
'f ram.dragon_hits 1 0x00904880 
'f ram.dragon_head_hpos 1 0x00904882 
'f ram.dragon_head_vpos 1 0x00904884 
'f ram.dragon_path_num 1 0x00904886 
'f ram.dragon_move_state 1 0x0090488c 
'f ram.dragon_facing 1 0x0090488e 
'f ram.dragon_state 1 0x00904890 
'f ram.dragon_anim_ctr 1 0x00904892 
'f ram.dragon_seg_mob_ids 1 0x00904894 
'f ram.level_flags 1 0x0090491c 
'f ram.level_flags_2 1 0x0090491d 
'f ram.level_flags_3 1 0x0090491e 
'f ram.level_flags_4 1 0x0090491f 
'f ram.it_player 1 0x009049dc 
'f ram.floorpattern 1 0x00904b5c 
'f ram.wallpattern 1 0x00904b5e 
'f ram.scroll_speed 1 0x00904f02 
'f ram.scroll_direction 1 0x00904f06 
'f ram.os_vblank_active 1 0x00904f0c 
'f ram.display_mode 1 0x00904f0e 
'f ram.text_effect_slots 1 0x00904f18 
'f ram.player_inputs_snapshot 1 0x00904f8a 
'f ram.sound_queue 1 0x00904f8e 
'f ram.eeprom_work 1 0x00904fa8 
'f ram.error_count 1 0x00904fc0 
'f ram.coin_counters 1 0x00904fec 
'f ram.coin_totals 1 0x00904ff0 
'f ram.coin_pending 1 0x00904ff4 
'f ram.vblank_counter 1 0x00904ff8 
'f ram.eeprom_dirty_flag 1 0x00904ffa 
'f ram.eeprom_config_ptr 1 0x00904ffc 
'f vram.alpha 1 0x00905000 
'f ram.player_supershot 1 0x00905f68 
'f vram.pf_vscroll_reg 1 0x00905f6e 
'f vram.color_alpha 1 0x00910000 
'f vram.color_mob 1 0x00910200 
'f vram.color_pf_shadow 1 0x00910400 
'f vram.color_pf 1 0x00910500 
'f vram.color_spare 1 0x00910600 
'f vram.pf_hscroll_reg 1 0x00930000 
fs *
# meta
CCu base64:TTY4MDEwIFZlY3RvciBUYWJsZSAtIFNTUD0weDkwNGYwMCwgUEM9MHg1ZTI= @ 0x00000000
CCu base64:T1MgQVBJIEp1bXAgVGFibGUgKEpNUCBpbnN0cnVjdGlvbnMgdG8gQVBJIGZ1bmN0aW9ucyk= @ 0x00000100
CCu base64:RGF0YSB0YWJsZTogUkFNL2hhcmR3YXJlIGFkZHJlc3MgcG9pbnRlcnMgKG5vdCBKTVAgZW50cmllcyk= @ 0x000001d8
CCu base64:Q2hlY2tzIGdhbWUgUk9NIGZvciBKTVAgYXQgMHg0MDAyNCwgZGlzcGF0Y2hlcyBpZiBwcmVzZW50 @ 0x00000300
CCu base64:R2FtZSBJUlExIGhvb2sgLSBjaGVja3MgMHg0MDAwYw== @ 0x00000314
CCu base64:R2FtZSBJUlEyIGhvb2sgLSBjaGVja3MgMHg0MDAxOA== @ 0x00000326
CCu base64:R2FtZSBJUlEzIGhvb2sgLSBjaGVja3MgMHg0MDAxMg== @ 0x00000338
CCu base64:VkJMQU5LOiBpZiBvc192YmxhbmtfYWN0aXZlIGdvdG8gb3NfdmJsYW5rX2hhbmRsZXIsIGVsc2UgZ2FtZSBob29r @ 0x0000034a
CCu base64:U291bmQvc2VsZi10ZXN0IElSUTogcmVhZHMgc291bmQgZGF0YSBvciBkaXNwYXRjaGVzIHRvIGdhbWU= @ 0x0000036c
CCu base64:VGVzdHMgVmlkZW8gUkFNIFNwYXJlLCBDb2xvciBSQU0sIFBsYXlmaWVsZCwgQWxwaGEsIE1PQiBSQU0= @ 0x000003a0
CCu base64:RGlzYWJsZSBpbnRlcnJ1cHRzLCByZXNldCBoYXJkd2FyZSwgY2hlY2sgc2VsZi10ZXN0IHN3aXRjaA== @ 0x000005e2
CCu base64:U2VsZi10ZXN0IG1vZGU6IHRob3JvdWdoIFJBTSB0ZXN0cyBiZWZvcmUgZW50ZXJpbmcgZGlhZ25vc3RpY3M= @ 0x0000061e
CCu base64:Q2xlYXIgUkFNLCBpbml0IGNvbG9ycywgUk9NIGNoZWNrc3VtLCBkZXRlY3QgZ2FtZSBST00sIGVudGVyIGdhbWUvT1M= @ 0x0000070c
CCu base64:U2V0cyBvc192YmxhbmtfYWN0aXZlLCBlbmFibGVzIElSUXMsIHJ1bnMgT1MgbWFpbiBsb29wIGNhbGxiYWNr @ 0x00000e14
CCu base64:QWNrIFZCTEFOSywgcGV0IHdhdGNoZG9nLCB1cGRhdGUgc2Nyb2xsIHJlZ3MsIHNuYXBzaG90IGlucHV0cw== @ 0x00000e5e
CCu base64:T1MgbWFpbiBsb29wOiBhdHRyYWN0IG1vZGUsIGNvaW4gaGFuZGxpbmcsIHNlbGYtdGVzdCBkaXNwYXRjaA== @ 0x0000129a
CCu base64:SG9vazogZ2FtZV9zdGFydHVwX2hvb2sxICgweDQwMDM2KSAtIGFmdGVyIGF0dHJhY3QgZGlzcGxheSBpbml0 @ 0x00001426
CCu base64:SG9vazogZ2FtZV9zdGFydHVwX2hvb2syICgweDQwMDJhKSAtIGFmdGVyIGNvaW4vdGV4dCBkaXNwbGF5IGluaXQ= @ 0x0000143e
CCu base64:SG9vazogZ2FtZV9zdGFydHVwX2hvb2szICgweDQwMDNjKSAtIGFmdGVyIHBhbGV0dGUgaW5pdA== @ 0x00001456
CCu base64:Q2xlYXJzIGFscGhhIFJBTSAoMHg5MDUwMDAtMHg5MDVGRkUpLCBmaWxscyBNT0IgUkFNIHdpdGggZ2FtZV9tb2JfZmlsbF92YWx1ZQ== @ 0x00001632
CCu base64:SG9vazogZ2FtZV9lZXByb21fY29uZmlnICgweDQwMDU0KSAtIHJldHVybnMgRUVQUk9NIGxheW91dCBjb25maWcgaW4gZDA= @ 0x000021a0
CCu base64:RUVQUk9NIHNldHRpbmdzIGJpdHMgNS03IHRhYmxlOiBtYXggbW9uc3RlcnMgcHJvY2Vzc2VkIHBlciBmcmFtZS4gOCByb3dzICh2YWx1ZSAwLTcpIHggNCBjb2xzIChwbGF5ZXJzLTEpLiBJbmRleCA9ICgoMHg5MDRBMjQmMHhFMCk+PjMpICsgcGxheWVycy0xLiBBZGRlZCB0byBiYXNlIDB4OTA0MDVGOyBjYXBwZWQgYXQgbGV2ZWwqMiAoZXhjZXB0IGx2bCAxKTsgZm9yY2VkIDAgb24gZnJhbWVfb3ZlcmZsb3coMHg5MDQ5MTYpLg== @ 0x00040e46
CCu base64:TGV2ZWwtdHJhbnNpdGlvbiBzZWNyZXQgcm9vbSBib29ra2VlcGluZy4gSWYgc2VjcmV0IHJvb20gd2FzIGFjdGl2ZSAoMHg5MDQwNjUpOiBwbGF5ZXIgZW50ZXJlZCAoMHg5MDQwNjM9MC0zKSAtPiBzZWNyZXRfcHJldl9tYXplKDB4OTA0ODcwKT1tYXplIywgc3RhcnQoMHg5MDQ4N0EpICs9IDE1IChtYXggNDApOyBub2JvZHkgZW50ZXJlZCAtPiBzdGFydCAtPSAyIChtaW4gNCkuIENvdW50ZG93bigweDkwNDg3OCkgPSBzdGFydC4gQ2FsbGVkIGZyb20gbWFpbl9zdGFydF9nYW1lKDB4NDgwRUMpIGFuZCBzaG93X2NvbnRpbnVlX3NjcmVlbiBlcGlsb2d1ZSgweDREOERDKS4gTmFtZSB2ZXJpZmllZCBieSBkaXNhc3NlbWJseTsgdXBkYXRlX2JnbV92b2x1bWUgcmVmdXRlZC4= @ 0x000486fe
CCu base64:cmVzb2x2ZV9zaG90X2hpdCh0YXJnZXQsIHNob290ZXIpIC0+IDAgPSBzaG90IGNvbnRpbnVlcyAocGllcmNlL3JlZmxlY3QpLCAtMSA9IHNob3QgY29uc3VtZWQuIHRhcmdldDogTU9CIHNsb3QsIG9yIDB4NDAwLTB4N0ZGID0gcGxheWZpZWxkIHRpbGUgKHdhbGwgYm91bmNlIHBhdGggMHg0QjQ5QSkuIHNob290ZXI6IDAtMyBwbGF5ZXIsID49NCBtb25zdGVyIHNob3QgY2xhc3MuIERhbWFnZTogcGxheWVyID0gdGJsIDB4NTk2QjZbY2hhcmFjdGVyICgrOCBpZiBwb3dlcnMgYml0MTIgc2hvdC1wb3dlcildICgrZ2V0cmFuZG9tKDIpIGlmIHRibCAweDU5NkMyKSwgc3VwZXJzaG90ICgweDkwNUY2OFtwXT4wKSBmb3JjZXMgMy4gVGFyZ2V0IHR5cGUgPSBtb2JfbGluaz4+MTAsIGRpc3BhdGNoIHZpYSBqdW1wIHRhYmxlIDB4NEIzMzYgKGJhc2UgMHg0QjMzOCkuIFBsYXllciB2aWN0aW1zIChocG9zJjB4Rj49MHhDLCB2aWN0aW0jID0gMHg5MDQwNjZbc2xvdF0+PjEwKTogbGV2ZWxfZmxhZ3NfNCBiaXQwID0gc2hvdHMgc3R1biAoKzB4Mjggc3R1bmRlbGF5IGNsYW1wIDB4NUEpLCBiaXQxID0gc2hvdHMgZGFtYWdlICgtMiBIUCk7IHN1cGVyc2hvdCBzaG9vdGVyIC0xMCBIUDsgbW9uc3RlciBzaG90cyB1c2UgZG1nIHRibCAweDU5NkNFW2NoYXIrNCphcm1vcit0aWVyKHNob3QgaHBvcyBiaXRzNC01KSs4KihjbGFzcz49OCldLiBNb25zdGVyczogaGVhbHRoID0gaHBvcyBsb3cgbmliYmxlLCB0aWVyIGJhc2UgdGJsIDB4NTg2NENbdHlwZV0sIG91dCBvZiBbYmFzZS0yLGJhc2VdID0gZGVzdHJveWVkIChpbXBhY3QgZnggMHg0N0RBRSArIG1vYmxpc3RfcmVtb3ZlKTsgc2NvcmUgPSBkYW1hZ2UgKiBtdWx0IChnaG9zdCAxMCwgZ3J1bnQtY2xhc3MgNSkgdmlhIHBsYXllcl9hZGRfc2NvcmVfd2l0aF9tdWx0OyBzb3JjL3N1cGVyc29yYyBpbW11bmUgd2hpbGUgYmxpbmtpbmcgKGhwb3MgYml0MTIpIHVubGVzcyBzdXBlcnNob3Q7IHN1cGVyc2hvdCBwaWVyY2VzIChyZXQgMCkgZXhjZXB0IERlYXRoL0lULiBEZWF0aDogZGVhdGhfaGl0cysrICgweDkwNEE1QyksIGRtZyBvbmx5IHZpYSBkZWF0aF9kYW1hZ2V0cmFjayB3L3N1cGVyc2hvdC4gR2VuZXJhdG9yczogdGllcjEgZGllcywgdGllcjIvMyBuZWVkIGRtZz49Mi8zIGVsc2UgZGVncmFkZSAobW9iX2xpbmsgLT0gZG1nPDwxMCArIHBpYyB1cGRhdGUpLiBNb3ZhYmxlIHdhbGw6IDI1IHBsYXllciBoaXRzICgweDkwNDA2NiArPSAweDQwMCB0byAweDY0MDApIHRoZW4gdHBvcnQgZGlzc29sdmUuIFNlY3JldCB3YWxsOiBzb3VuZCAweDMwLCByZXZlYWwgKyByYW5kb20gcHJpemUgZDY9cmFuZCgxNikgaWYgPCBwbGF5ZXJzKjIrMjogMC0xIERFQVRILCAyLTMgdHJlYXN1cmUgYmFnLCA0LzggaW52dWxuIHBvdGlvbiwgNS83IGludnVsbiBmb29kLCBlbHNlIGhpZGRlbiBwb3Rpb24gKHBpY3MgdGJsIDB4NTg2OEMsIHNwYXduIHRibCAweDU4NjBDKS4gRGVzdHJ1Y3RpYmxlIHdhbGw6IGNydW1ibGUgdmlhIDB4NTMwM0EodGFyZ2V0LGRtZykuIERvb3JzOiByZWFjdCBvbmx5IGlmIG9uLXNjcmVlbiAoMHg0QUVBMCkuIEZvb2QvcG90czogZGVzdHJveWVkICsgc3BlZWNoOyBwb2lzb24gdmFyaWFudHMgKHBpYyAweDI1RUQgZm9vZC8weDIwRkMgcG90KSBzZXQgcG9pc29uX3RpbWVyIDB4OTA0OEIyID0gMHgyNTgvMHg0QjAuIFRyZWFzdXJlL2ludnVsbiBpdGVtcyBuZWVkIHN1cGVyc2hvdC4gRHJhZ29uIC0+IGRyYWdvbl9zaG90X2hpdCAweDU0MTEyLiBSZWZsZWN0IHBvd2VyIChwb3dlcnMgYml0MTApOiBuZXcgZGlyIHZpYSAweDUzODE4IC0+IHNob3QgYm91bmNlcyBvZmYgd2FsbHMuIE1heC10aWVyIHNob3RzIChzaG90IGhwb3MmMHgzMD09MHgzMCkgcGFzcyB0aHJvdWdoIHdhbGxzLiBTZWNyZXQgdHJpY2tzICgweDkwNDA2NSk6IDU9c2hvb3QgZm9vZCwgOT1oaXQgYnkgc3Ryb25nIHNob3QsIDB4MTE9c2hvb3QgcGxheWVyLCAweDVBPXN1cGVyc2hvdCB0cmVhc3VyZSAtPiBwcm9ncmVzcyBpbiAweDkwNDg3MltwXS4gZXNjYXBlX3RpbWVyICsgaWRsZV90aW1lciByZXNldCBvbiBraWxscy4= @ 0x0004af50
CCu base64:TWF6ZSBSTEUgZGVjb2RlciwgYXJnID0gbWF6ZSBkYXRhIHB0ci4gQ29waWVzIGhlYWRlciBIVDEvSFQyL1ZUMS9WVDIgKG9mZnNldHMgNyw4LDksMHhBKSB0byAweDkwNDg2Ni82OC82QS82Qy4gbGFzdF90eXBlIGluaXQgPSBIVDIuIEN1cnNvciBzdGFydHMgc2xvdCAweDIwLCBkYXRhIGF0ICsweEIsIGxvb3AgdW50aWwgY3Vyc29yID49IDB4NDAwLiBCeXRlY29kZSBiLCBuNT1iJjB4MUYsIG40PWImMHhGOiAwMC0zRiBhZGQgZWxlbWVudCBiJjB4M0Ygb25jZSwgbGFzdD1iLiA0MC03Rjogc2VsPShiPj40KSYzIC0+IHB0ciB0YWJsZSAweDU5QjU0IFtIVDEsVlQxLEhUMixWVDJdLCB0PWhlYWRlciBieXRlLCBsYXN0PXQsIE49bjQrMTsgdCYweEMwOiAwMD13cml0ZSBOIG9mIHQmMHgzRiAodmVydGljYWwgd3JpdGVyIGlmIGIgYml0NCBzZXQpLCA0MD1OIHNraXBzIHRoZW4gMSBvZiB0LCA4MD0xIG9mIHQgdGhlbiBOIHNraXBzLCBDMD1OIHdhbGxzKHR5cGUyKSB0aGVuIDEgb2YgdC4gODAtOUYgcmVwZWF0IGxhc3QgbjUrMSAoMS0zMikgaG9yaXouIEEwLUFGIGhvcml6IHdhbGwgcnVuIG40KzEuIEIwLUJGIHZlcnQgd2FsbCBydW4gbjQrMS4gQzAtREYgc2tpcCBuNSsxIChOTyB3YWxsIC0gZG9jIHdhcyB3cm9uZykuIEUwLUZGIHNraXAgbjUrMSB0aGVuIDEgd2FsbC4gV3JpdGVyczogbWF6ZV90aWxlX3dyaXRlKHNsb3QsdHlwZSxjb3VudCk9aG9yaXpvbnRhbCBjb25zZWN1dGl2ZSwgcmV0dXJucyBuZXh0IHNsb3QsIHR5cGUwPWFkdmFuY2Ugb25seSwgc3VwcHJlc3NlcyBlbGVtZW50IDB4M0MgKERSQUdPTikgd2hlbiBnYW1lX21vZGU9MCBhbmQgbGV2ZWw8MTI7IG1hemVfdGlsZV93cml0ZV9hdD12ZXJ0aWNhbCwgc3RyaWRlIDMyICgzMSBpZiBvZGQtYW5nbGU6IGZsYWdzIGxvbmcgMHg5MDQ5MUMgYml0MjYgKyBmbGFnc180IGJpdDUpLCByZXR1cm5zIHNsb3QrMS4= @ 0x0004c1bc
CCu base64:U2VjcmV0IHJvb20gd2lubmVyIG5hbWUtZW50cnkgc2V0dXAuIElmIEVFUFJPTSBzZXR0aW5ncygweDkwNEEyNCkgYml0MTMgc2V0OiBuYW1lIGJ1ZmZlciAweDkwNEFBNCA9ICdBJysyOCBzcGFjZXMsIHBsYXllcl9zdGF0dXMoMHg5MDQ5QTArcCk9MHgyMCAoZW50ZXJpbmcgbmFtZSksIGRlbGF5KDB4OTA0QTRFKT0weEE4RCwgZHJhd3MgRU5URVIgWU9VUiAvICdMQVNULU5BTUUgRklSU1QtTkFNRScgdmlhIE9TIGNhbGxzLiBCaXQxMyBjbGVhcjogcGxheWVyX3N0YXR1cz0yLCBkZWxheT0weDM4NSwgc2VjcmV0X3Jvb21fcGxheWVyKDB4OTA0MDYzKT0weEZGLiBOYW1lIHZlcmlmaWVkIGJ5IGRpc2Fzc2VtYmx5OyByZXNldF9hdHRyYWN0X3BsYXllciByZWZ1dGVkLg== @ 0x00054ec6
CCu base64:MTIgdGlwIHJlY29yZHMsIGVhY2ggPSAzIGxvbmd3b3JkIHN0cmluZyBwdHJzIChudWxsID0gdW51c2VkIGxpbmUpICsgaW5saW5lIHN0cmluZ3MuIFB0ciB0YWJsZSBhdCAweDU4MTVDICgxMiBsb25nczsga25vd25faXNzdWVzIHNhaWQgMHg1ODE1NCB3aGljaCBpbmNsdWRlcyAyIHVucmVsYXRlZCBsb25ncyA1LDMpLiBSZWNvcmRzIHNwYW4gMHg1ODI4Qy0weDU4NTBDLiAwOiBCTFVFL1NFTEVDVEVELS9FTEYgKGpvaW4gYmFubmVyIHRlbXBsYXRlKSwgMTogUFVTSCBNT1ZBQkxFIFdBTExTLCAyOiBTT01FIFRSRUFTVVJFIFJFUVVJUkVTIEtFWVMsIDM6IFRIRVJFIENBTiBCRSBNT1JFIFRIQU4gT05FIFRSQVAsIDQ6IEFDSUQgUFVERExFUyBNT1ZFIFJBTkRPTUxZLCA1OiBTT01FIFdBTExTIENBTiBCRSBTSE9UIEFORCBUVVJOIElOVE8gR09PRCBPUiBCQUQsIDY6IERFQVRIIERJRVMgQUZURVIgVEFLSU5HIFVQIFRPIDIwMCBIRUFMVEgsIDc6IEhBVkUgRlJJRU5EUyBKT0lOIElOIEFOWSBUSU1FLCA4OiBNT05TVEVSUyBGT0xMT1cgUExBWUVSIFdITyBJUyBJVCwgOTogU09NRSBXQUxMUyBNT1ZFIFJBTkRPTUxZLCAxMDogTU9OU1RFUlMgTUFZIE1PVkUgRElGRkVSRU5UTFksIDExOiBUQUcgWU9VUkUgSVQuIDB4NTgyNUUtMHg1ODI4QiA9IHNlcGFyYXRlIHVuaWRlbnRpZmllZCB3b3JkIHRhYmxlLg== @ 0x0005828c
CCu base64:RHJhZ29uIHBhdGggcHJvZ3JhbXM6IDUgcm93cyB4IDE2IGJ5dGVzIChOT1QgMTI4eDE2KS4gUm93IHNlbGVjdGVkIGJ5IHJhbS5kcmFnb25fcGF0aF9udW0gKDB4OTA0ODg2LCAwLTQ7IHJhbmRvbSAwLTQgb24gZWFjaCBoaXQpLiBCeXRlIGluZGV4ID0gZHJhZ29uX2FuaW1fY3RyKDB4OTA0ODkyKT4+MyAocGhhc2UgYWR2YW5jZXMgZXZlcnkgOCBmcmFtZXMsIGN0ciB3cmFwcyBhdCAxMjgpLiBCeXRlIGZvcm1hdDogYml0MCA9IGZpcmUgdHJpZ2dlciwgYml0cyAzLTEgKGJ5dGU+PjEpID0gaGVhZCBwb3NlIDAtMy4gSGVhZCBkcmF3OiBpZHggPSBieXRlICsgZmFjaW5nKjQgLT4gcGljcyAweDVENTI4LCBocG9zIGRlbHRhIDB4NUQ0MzgsIHZwb3MgZGVsdGEgMHg1RDQ3OCAoYWRkZWQgdG8gZHJhZ29uIE1PQiBwb3MgLT4gaGVhZCBwb3MgMHg5MDQ4ODIvODQpLiBGaXJlOiB3aGVuIGJpdDAgc2V0LCBjb29sZG93biAweDkwNDg3Qz09MCwgKDB4OTA0ODhDJjB4Rik8NDogYWxsb2Mgc2hvdCAweDU0MEU4IHRoZW4gZHJhZ29uX2ZpcmVfc2V0dXAoMHg1NDc0OCk6IGNvb2xkb3duPTgsIHNwYXduIHNlZ21lbnQgPSB3b3JkWzB4OTA0ODk0ICsgdGJsXzB4NUQ0QjhbcG9zZStmYWNpbmcqMl0qMl0sIHNob3QgZGlyID0gZmFjaW5nLiBXaGlsZSBsb2NrZWQtaW4gKHN0YXRlIGJpdDMpLCBmaXJlIGJ5dGVzIGhvbGQgdGhlIGNvdW50ZXIgdW50aWwgY29vbGRvd24gZXhwaXJlcy4gRHJhZ29uIG9ubHkgdGFrZXMgaGl0cyB3aGlsZSBmaXJlIGJpdCBzZXQgYW5kIG5vdCBzbGVlcGluZy90dXJuaW5nOyA5IGhpdHMgPSBkZWF0aDsgb24gaGl0IG5ldyByYW5kb20gcGF0aCBmYXN0LWZvcndhcmRlZCB0byBtYXRjaGluZyBieXRlIGZvciBwb3NlIGNvbnRpbnVpdHku @ 0x0005d578
CCu base64:cmVmcmVzaF90aWxlX3Zpc3VhbChkMD1zbG90LCBkMT1vYmp0eXBlKTogcmVkcmF3cyBvbmUgcGxheWZpZWxkIHRpbGUuIEZpeGVkIGRlc2NyaXB0b3JzOiB0cmFuc3BvcnRlcigweDNFKS0+MHg1Q0FBOCBhdHRyIDB4NDAwMCwgZXhpdCgweDEwKS0+MHg1QzhBMCwgZXhpdHRvNigweDExKS0+MHg1QzhBOCwgZm9yY2VmaWVsZCBodWIoMHgzRiktPiBwdHIgdGJsIDB4NUJBNzBbKDB4OTA0MDY2W3Nsb3RdPj4yKSYweEZdLiBGbG9vci90cmFwcyAoMCwweEEtMHhDLDEpIC0+IHBmX2Zsb29yX2RyYXcgKDB4NUU4ODggcmVnLzB4NUU4OTIgc3RhY2spOiBkZXNjcmlwdG9yIHdvcmRzIGZyb20gZmxvb3JfZGVzY19iYXNlIDB4NUJBRTAgKCt2YXJpYW50IGZyb20gd2FsbCBwcm94aW1pdHkpLCBmaW5hbCB0aWxlIGNvZGUgKz0gZmxvb3JwYXR0ZXJuKDB4OTA0QjVDKSoweDMwICsgYXR0ci4gV2FsbHMgKDIrKSAtPiBwZl93YWxsX2RyYXcgKDB4NUVBQjggcmVnLzB4NUVBQzIgc3RhY2spOiBidWlsZHMgOC1uZWlnaGJvciBjb25uZWN0aXZpdHkgbWFzayAobmVpZ2hib3IgPSBwaWMhPTB4ODAwMCBvciBsaW5rIHR5cGUgMHgzRiksIHZhcmlhbnQgYnl0ZSA9IHdhbGxfY29ubl92YXJpYW50X3RibCAweDVFRTI0IChvciAweDVFRjI0IGZvciBwYXR0ZXJucyA2LzB4Qik7IGRlc2NyaXB0b3IgYmFzZSBieSB3YWxscGF0dGVybigweDkwNEI1RSk6IDw2IC0+IHdhbGxfZGVzY19ibG9ja3MgMHg1QkJFMCArIHdhbGxfcGF0dGVybl9vZmZzZXRzIDB4NUVERDRbcGF0XSAoMHg0NC11bml0IHN0cmlkZSksIDYgLT4gMHg1RDJGOCwgZGVzdHJ1Y3RpYmxlIHR5cGU1IHcvcGF0Pj02IC0+IDB4NUQzRDAsIDctMHhBLzB4QysgLT4gcmFuZG9tIG9mIDYgcHRyIHNldHMgYXQgMHg1RURGNCAoKzB4MTggZm9yIHBhdCA3KTsgZGVzY3JpcHRvciA9IGJhc2UgKyB2YXJpYW50Kjg7IHdyaXRlcyBUTC9CTC9UUi9CUiB3b3JkcyArMHg3MDAwIHRvIHZyYW0ucGxheWZpZWxkICsgeSoyNTYgKyB4KjQuIEludmlzaWJsZSB3YWxsczogc2tpcHBlZCB3aGVuIExGTEFHMiBiaXQ3IChhbGwpIG9yIExGTEFHMSBiaXQ3ICh0cmFwIHdhbGxzLCB0eXBlcyA3LTkpIHVubGVzcyBsZXZlbCA5OTk5LiBUaGVuIHVwZGF0ZXMgbmVpZ2hib3JpbmcgZG9vcnMgKyB3YWxscy4= @ 0x0005f5a0
CCu base64:RG9vciB0aWxlIGdyYXBoaWMgdXBkYXRlci4gQXJncyAoeCx5LGRvb3J0eXBlIGZyb20gcGZfaXNkb29yKS4gVHlwZSAxIChwaWNzIDB4OUQxOC0weDlEMzgpOiBidWlsZHMgNC1iaXQgYWRqYWNlbnQtZG9vciBtYXNrIChMPTIsZG93bj00LFI9OCx1cD0weDEwKSB2aWEgcGZfaXNkb29yLCBwaWN0dXJlID0gZG9vcl9nZnhfYnlfbmVpZ2hib3JzW21hc2tdICgweDVGOUNFKSwgd3JpdGVzIHZyYW0gcGljdHVyZS9ocG9zL3Zwb3MgZm9yIHRpbGUsIHN0b3JlcyBtYXNrIGluIGJpdHMgMTAtMTMgb2YgMHg5MDQwNjZbdGlsZV0gKGxvdyAxMCBiaXRzIGtlcHQpLiBUeXBlcyAyLzMgd2l0aCBubyBkb29yIG5laWdoYm9yOiBvcmllbnRhdGlvbiBmcm9tIHN1cnJvdW5kaW5nIHBsYWluLWZsb29yIHRpbGVzIChwZl9pc2JsYW5rZmxvb3IgMHg1RUEyRSksIHR5cGUtMiB0YWJsZSAweDVGQUNBLCB0eXBlLTMgdnBvcyBvZmZzZXQgdGFibGVzIDB4NUZCRUUvMHg1RkMwMC4gRW50cnkgMHg1Rjg3NiB0YWtlcyBhMD14LGExPXksZDA9dHlwZS4gQ2FsbGVkIGJ5IG1hemVfZG9vcnNfc2V0dXAgKGFsbCB0aWxlcykgYW5kIHBmX2Rvb3JfdXBkYXRlX3N1cnJvdW5kaW5nICg0IG5laWdoYm9ycyBvZiBjaGFuZ2VkIHRpbGUpLg== @ 0x0005f880
CCu base64:RGlhbG9nICJzaG93biBvbmNlIiBXT1JEIGJpdGZpZWxkIChjb3ZlcnMgR1JLJ3MgaXRlbV9kbGdfZmxhZ3MrcG93ZXJfZGxnX2ZsYWdzIGJ5dGVzKS4gQml0IHRlc3RlZC9zZXQgYnkgZGlhbG9nX2ZpcnN0X2VuY291bnRlciBjb2RlICgweDRDNDgyIG9yaSAjMSA9IGRyYWdvbiBlbmNvdW50ZXIgZGlhbG9nIC0gUkVQT1JUJ3MgImRyYWdvbl9lbmNvdW50ZXJfZmxhZyIgYml0KS4gQ2xlYXJlZCBieSBtYXplX25ld19sZXZlbF9zZXR1cCAoMHg0MzhFMCwgYml0IDAgb25seSkgYW5kIGZ1bGx5IGF0IDB4NDQyM0MvMHg0NDlFRS4= @ 0x0090487e
CCu base64:bGV2ZWxfZmxhZ3MgbG9uZyAoPSAibWF6ZV9waWNrdXBfY29uZmlnIikgPSBtYXplIGhlYWRlciBieXRlcyAxLTQgYXNzZW1ibGVkIGJ5IG1hemVfbG9hZF9waWNrdXBfY29uZmlnLiBCeXRlIDA9TEZMQUcxIChvZGQtYW5nbGUgYml0czAtNiwgYml0NyBpbnZpcyB0cmFwd2FsbHMpLCAxPUxGTEFHMiAoZmFzdCBiaXRzMC02LCBiaXQ3IGludmlzIGFsbCB3YWxscyksIDI9TEZMQUczIChiaXRzMC0yIHJhbmRvbSBmb29kIGNvdW50LCBiaXQzIGN5Y2xpYyB3YWxscywgYml0czQtNSBkZWxldGFibGUgd2FsbHMsIGJpdDYgZXhpdCBtb3ZlcywgYml0NyBleGl0IGNob29zZS1vbmUpLCAzPUxGTEFHNCAoYml0MCBzaG90cyBzdHVuLCBiaXQxIHNob3RzIGh1cnQsIGJpdDIgdHJhcHMgbG9jYWwsIGJpdDMgdHJhcHMgcmFuZG9tLCBiaXQ0IHdyYXAtViwgYml0NSB3cmFwLUgsIGJpdDYgZmFrZSBleGl0cywgYml0NyBvZmZzY3JlZW4pLiBSYW5kb21pemVkIHBlciBsZXZlbDogYml0cyAyNi0yNyBYT1IgcmFuZCg0KTsgZGVlcCBsZXZlbHMgT1IgZ2V0X3JhbmRvbV9tYXplX2ZsYWdzICsgMHgzMC8weEIwIHVubGVzcyBMRkxBRzQgYml0Mi4gRVhJVF9NT1ZFUyBjbGVhcmVkIGJ5IG1hemVfc2Nhbl9vYmplY3RzIHdoZW4gb25seSAxIGV4aXQgKE5PVCAiaGFzIGZvb2QiIC0ga25vd25faXNzdWVzIDQuNSB3YXMgd3JvbmcpLg== @ 0x0090491c
# types
'tk *aligned_alloc=func
'tk FILE=type
'tk NSString=struct
'tk _Exit=func
'tk _exit=func
'tk _sSS10FoundationE19_bridgeToObjectiveCSo8NSStringCyF=func
'tk abort=func
'tk abs=func
'tk access=func
'tk acl_free=func
'tk acos=func
'tk acosf=func
'tk acosh=func
'tk acoshf=func
'tk acoshl=func
'tk acosl=func
'tk arc4random=func
'tk asctime=func
'tk asin=func
'tk asinf=func
'tk asinh=func
'tk asinhf=func
'tk asinhl=func
'tk asinl=func
'tk assert_fail=func
'tk assert_rtn=func
'tk at_quick_exit=func
'tk atan=func
'tk atan2=func
'tk atan2f=func
'tk atan2l=func
'tk atanf=func
'tk atanh=func
'tk atanhf=func
'tk atanhl=func
'tk atanl=func
'tk atexit=func
'tk atof=func
'tk atoi=func
'tk atol=func
'tk atoll=func
'tk basename=func
'tk bind=func
'tk bindtextdomain=func
'tk bsearch=func
'tk btowc=func
'tk bzero=func
'tk calloc=func
'tk cbrt=func
'tk cbrtf=func
'tk cbrtl=func
'tk ceil=func
'tk ceilf=func
'tk ceill=func
'tk char=type
'tk char *=type
'tk char **=type
'tk chmod=func
'tk clearerr=func
'tk clock=func
'tk close=func
'tk compat_mode=func
'tk connect=func
'tk copysign=func
'tk copysignf=func
'tk copysignl=func
'tk cos=func
'tk cosf=func
'tk cosh=func
'tk coshf=func
'tk coshl=func
'tk cosl=func
'tk ctime=func
'tk difftime=func
'tk div=func
'tk double=type
'tk erf=func
'tk erfc=func
'tk erfcf=func
'tk erfcl=func
'tk erff=func
'tk erfl=func
'tk err=func
'tk errc=func
'tk error=func
'tk errx=func
'tk exit=func
'tk exp=func
'tk exp2=func
'tk exp2f=func
'tk exp2l=func
'tk expf=func
'tk expl=func
'tk expm1=func
'tk expm1f=func
'tk expm1l=func
'tk fabs=func
'tk fabsf=func
'tk fabsl=func
'tk fchmod=func
'tk fclose=func
'tk fdim=func
'tk fdimf=func
'tk fdiml=func
'tk feclearexcept=func
'tk fegetenv=func
'tk fegetexceptflag=func
'tk fegetround=func
'tk feholdexcept=func
'tk feof=func
'tk feraiseexcept=func
'tk ferror=func
'tk fesetenv=func
'tk fesetexceptflag=func
'tk fesetround=func
'tk fetestexcept=func
'tk feupdateenv=func
'tk fflagtostr=func
'tk fflush=func
'tk fflush_unlocked=func
'tk fgetc=func
'tk fgetpos=func
'tk fgets=func
'tk fgetwc=func
'tk fgetws=func
'tk fileno=func
'tk float=type
'tk floor=func
'tk floorf=func
'tk floorl=func
'tk fma=func
'tk fmaf=func
'tk fmal=func
'tk fmax=func
'tk fmaxf=func
'tk fmaxl=func
'tk fmin=func
'tk fminf=func
'tk fminl=func
'tk fmod=func
'tk fmodf=func
'tk fmodl=func
'tk fopen=func
'tk fpclassify=func
'tk fprintf=func
'tk fputc=func
'tk fputs=func
'tk fputwc=func
'tk fputws=func
'tk fread=func
'tk free=func
'tk freopen=func
'tk frexp=func
'tk frexpf=func
'tk frexpl=func
'tk fscanf=func
'tk fseek=func
'tk fsetpos=func
'tk fstat=func
'tk ftell=func
'tk fts_children_INODE64=func
'tk fts_close_INODE64=func
'tk fts_open_INODE64=func
'tk fts_read_INODE64=func
'tk fts_set_INODE64=func
'tk func=type
'tk func.*aligned_alloc.arg.0=size_t,alignment
'tk func.*aligned_alloc.arg.1=size_t,size
'tk func.*aligned_alloc.args=2
'tk func.*aligned_alloc.ret=void
'tk func._Exit.arg.0=int,status
'tk func._Exit.args=1
'tk func._Exit.noreturn=true
'tk func._Exit.ret=void
'tk func._exit.arg.0=int,status
'tk func._exit.args=1
'tk func._exit.noreturn=true
'tk func._exit.ret=void
'tk func._sSS10FoundationE19_bridgeToObjectiveCSo8NSStringCyF.arg.0=void *
'tk func._sSS10FoundationE19_bridgeToObjectiveCSo8NSStringCyF.args=1
'tk func._sSS10FoundationE19_bridgeToObjectiveCSo8NSStringCyF.ret=void *
'tk func.abort.args=0
'tk func.abort.noreturn=true
'tk func.abort.ret=void
'tk func.abs.arg.0=int,j
'tk func.abs.args=1
'tk func.abs.ret=int
'tk func.access.arg.0=const char *,path
'tk func.access.arg.1=int,mode
'tk func.access.args=2
'tk func.access.ret=int
'tk func.acl_free.arg.0=void *,obj_p
'tk func.acl_free.args=1
'tk func.acl_free.ret=int
'tk func.acos.arg.0=arithmetic,x
'tk func.acos.args=1
'tk func.acos.ret=floating_point
'tk func.acosf.arg.0=float,x
'tk func.acosf.args=1
'tk func.acosf.ret=float
'tk func.acosh.arg.0=arithmetic,x
'tk func.acosh.args=1
'tk func.acosh.ret=floating_point
'tk func.acoshf.arg.0=float,x
'tk func.acoshf.args=1
'tk func.acoshf.ret=float
'tk func.acoshl.arg.0=long double,x
'tk func.acoshl.args=1
'tk func.acoshl.ret=long double
'tk func.acosl.arg.0=long double,x
'tk func.acosl.args=1
'tk func.acosl.ret=long double
'tk func.arc4random.args=0
'tk func.arc4random.ret=uint32_t
'tk func.asctime.arg.0=const tm *,timeptr
'tk func.asctime.args=1
'tk func.asctime.ret=char *
'tk func.asin.arg.0=arithmetic,x
'tk func.asin.args=1
'tk func.asin.ret=floating_point
'tk func.asinf.arg.0=float,x
'tk func.asinf.args=1
'tk func.asinf.ret=float
'tk func.asinh.arg.0=arithmetic,x
'tk func.asinh.args=1
'tk func.asinh.ret=floating_point
'tk func.asinhf.arg.0=float,x
'tk func.asinhf.args=1
'tk func.asinhf.ret=float
'tk func.asinhl.arg.0=long double,x
'tk func.asinhl.args=1
'tk func.asinhl.ret=long double
'tk func.asinl.arg.0=long double,x
'tk func.asinl.args=1
'tk func.asinl.ret=long double
'tk func.assert_fail.arg.0=const char *,assertion
'tk func.assert_fail.arg.1=const char *,file
'tk func.assert_fail.arg.2=unsigned int,line
'tk func.assert_fail.arg.3=const char *,function
'tk func.assert_fail.args=4
'tk func.assert_fail.noreturn=true
'tk func.assert_fail.ret=void
'tk func.assert_rtn.arg.0=const char *,assertion
'tk func.assert_rtn.arg.1=const char *,file
'tk func.assert_rtn.arg.2=unsigned int,line
'tk func.assert_rtn.arg.3=const char *,function
'tk func.assert_rtn.args=4
'tk func.assert_rtn.cc=amd64
'tk func.assert_rtn.noreturn=true
'tk func.assert_rtn.ret=void
'tk func.at_quick_exit.args=0
'tk func.at_quick_exit.ret=int
'tk func.atan.arg.0=arithmetic,x
'tk func.atan.args=1
'tk func.atan.ret=floating_point
'tk func.atan2.arg.0=arithmetic,y
'tk func.atan2.arg.1=arithmetic,x
'tk func.atan2.args=2
'tk func.atan2.ret=floating_point
'tk func.atan2f.arg.0=float,y
'tk func.atan2f.arg.1=float,x
'tk func.atan2f.args=2
'tk func.atan2f.ret=float
'tk func.atan2l.arg.0=long double,y
'tk func.atan2l.arg.1=long double,x
'tk func.atan2l.args=2
'tk func.atan2l.ret=long double
'tk func.atanf.arg.0=float,x
'tk func.atanf.args=1
'tk func.atanf.ret=float
'tk func.atanh.arg.0=arithmetic,x
'tk func.atanh.args=1
'tk func.atanh.ret=floating_point
'tk func.atanhf.arg.0=float,x
'tk func.atanhf.args=1
'tk func.atanhf.ret=float
'tk func.atanhl.arg.0=long double,x
'tk func.atanhl.args=1
'tk func.atanhl.ret=long double
'tk func.atanl.arg.0=long double,x
'tk func.atanl.args=1
'tk func.atanl.ret=long double
'tk func.atexit.arg.0=func,function
'tk func.atexit.args=1
'tk func.atexit.ret=int
'tk func.atof.arg.0=const char *,str
'tk func.atof.args=1
'tk func.atof.ret=double
'tk func.atoi.arg.0=const char *,str
'tk func.atoi.args=1
'tk func.atoi.ret=int
'tk func.atol.arg.0=const char *,str
'tk func.atol.args=1
'tk func.atol.ret=long
'tk func.atoll.arg.0=const char *,str
'tk func.atoll.args=1
'tk func.atoll.ret=long long
'tk func.basename.arg.0=char *,path
'tk func.basename.args=1
'tk func.basename.ret=char *
'tk func.bind.arg.0=int,socket
'tk func.bind.arg.1=struct sockaddr*,address
'tk func.bind.arg.2=socklen_t,address_len
'tk func.bind.args=3
'tk func.bind.ret=int
'tk func.bindtextdomain.arg.0=char *,domainname
'tk func.bindtextdomain.arg.1=char *,dirname
'tk func.bindtextdomain.args=2
'tk func.bindtextdomain.ret=char *
'tk func.bsearch.arg.0=const void *,key
'tk func.bsearch.arg.1=const void *,base
'tk func.bsearch.arg.2=size_t,nmemb
'tk func.bsearch.arg.3=size_t,size
'tk func.bsearch.arg.4=int,(*compar)(const void *,const void *)
'tk func.bsearch.args=5
'tk func.btowc.arg.0=int,c
'tk func.btowc.args=1
'tk func.btowc.ret=wint_t
'tk func.bzero.arg.0=void *,s
'tk func.bzero.arg.1=size_t,n
'tk func.bzero.args=2
'tk func.bzero.ret=void
'tk func.calloc.arg.0=size_t,nmeb
'tk func.calloc.arg.1=size_t,size
'tk func.calloc.args=2
'tk func.calloc.ret=void *
'tk func.cbrt.arg.0=arithmetic,x
'tk func.cbrt.args=1
'tk func.cbrt.ret=floating_point
'tk func.cbrtf.arg.0=float,x
'tk func.cbrtf.args=1
'tk func.cbrtf.ret=float
'tk func.cbrtl.arg.0=long double,x
'tk func.cbrtl.args=1
'tk func.cbrtl.ret=long double
'tk func.ceil.arg.0=arithmetic,x
'tk func.ceil.args=1
'tk func.ceil.ret=floating_point
'tk func.ceilf.arg.0=float,x
'tk func.ceilf.args=1
'tk func.ceilf.ret=float
'tk func.ceill.arg.0=long double,x
'tk func.ceill.args=1
'tk func.ceill.ret=long double
'tk func.chmod.arg.0=const char *,path
'tk func.chmod.arg.1=int,mode
'tk func.chmod.args=2
'tk func.chmod.ret=int
'tk func.clearerr.arg.0=FILE *,stream
'tk func.clearerr.args=1
'tk func.clearerr.ret=void
'tk func.clock.args=0
'tk func.clock.ret=clock_t
'tk func.close.arg.0=int,fildes
'tk func.close.args=1
'tk func.close.ret=int
'tk func.compat_mode.arg.0=const char *,function
'tk func.compat_mode.arg.1=const char *,mode
'tk func.compat_mode.args=2
'tk func.compat_mode.ret=bool
'tk func.connect.arg.0=int,socket
'tk func.connect.arg.1=void *,addr
'tk func.connect.arg.2=size_t,addrlen
'tk func.connect.args=3
'tk func.connect.ret=ssize_t
'tk func.copysign.arg.0=arithmetic,x
'tk func.copysign.arg.1=arithmetic,y
'tk func.copysign.args=2
'tk func.copysign.ret=floating_point
'tk func.copysignf.arg.0=float,x
'tk func.copysignf.arg.1=float,y
'tk func.copysignf.args=2
'tk func.copysignf.ret=float
'tk func.copysignl.arg.0=long double,x
'tk func.copysignl.arg.1=long double,y
'tk func.copysignl.args=2
'tk func.copysignl.ret=long double
'tk func.cos.arg.0=arithmetic,x
'tk func.cos.args=1
'tk func.cos.ret=floating_point
'tk func.cosf.arg.0=float,x
'tk func.cosf.args=1
'tk func.cosf.ret=float
'tk func.cosh.arg.0=arithmetic,x
'tk func.cosh.args=1
'tk func.cosh.ret=floating_point
'tk func.coshf.arg.0=float,x
'tk func.coshf.args=1
'tk func.coshf.ret=float
'tk func.coshl.arg.0=long double,x
'tk func.coshl.args=1
'tk func.coshl.ret=long double
'tk func.cosl.arg.0=long double,x
'tk func.cosl.args=1
'tk func.cosl.ret=long double
'tk func.ctime.arg.0=const time_t *,timer
'tk func.ctime.args=1
'tk func.ctime.ret=char *
'tk func.difftime.arg.0=time_t,time1
'tk func.difftime.arg.1=time_t,time0
'tk func.difftime.args=2
'tk func.difftime.ret=double
'tk func.div.arg.0=int,numer
'tk func.div.arg.1=int,denom
'tk func.div.args=2
'tk func.div.ret=div_t
'tk func.erf.arg.0=arithmetic,x
'tk func.erf.args=1
'tk func.erf.ret=floating_point
'tk func.erfc.arg.0=arithmetic,x
'tk func.erfc.args=1
'tk func.erfc.ret=floating_point
'tk func.erfcf.arg.0=float,x
'tk func.erfcf.args=1
'tk func.erfcf.ret=float
'tk func.erfcl.arg.0=long double,x
'tk func.erfcl.args=1
'tk func.erfcl.ret=long double
'tk func.erff.arg.0=float,x
'tk func.erff.args=1
'tk func.erff.ret=float
'tk func.erfl.arg.0=long double,x
'tk func.erfl.args=1
'tk func.erfl.ret=long double
'tk func.err.arg.0=int,eval
'tk func.err.arg.1=const char *,fmt
'tk func.err.args=2
'tk func.err.noreturn=true
'tk func.err.ret=void
'tk func.errc.arg.0=int,eval
'tk func.errc.arg.1=int,code
'tk func.errc.arg.2=const char *,fmt
'tk func.errc.args=3
'tk func.errc.noreturn=true
'tk func.errc.ret=void
'tk func.error.arg.0=int,status
'tk func.error.arg.1=int,errname
'tk func.error.arg.2=char *,format
'tk func.error.args=3
'tk func.error.ret=void
'tk func.errx.arg.0=int,eval
'tk func.errx.arg.1=const char *,fmt
'tk func.errx.args=2
'tk func.errx.noreturn=true
'tk func.errx.ret=void
'tk func.exit.arg.0=int,status
'tk func.exit.args=1
'tk func.exit.noreturn=true
'tk func.exit.ret=void
'tk func.exp.arg.0=arithmetic,x
'tk func.exp.args=1
'tk func.exp.ret=floating_point
'tk func.exp2.arg.0=arithmetic,x
'tk func.exp2.args=1
'tk func.exp2.ret=floating_point
'tk func.exp2f.arg.0=float,x
'tk func.exp2f.args=1
'tk func.exp2f.ret=float
'tk func.exp2l.arg.0=long double,x
'tk func.exp2l.args=1
'tk func.exp2l.ret=long double
'tk func.expf.arg.0=float,x
'tk func.expf.args=1
'tk func.expf.ret=float
'tk func.expl.arg.0=long double,x
'tk func.expl.args=1
'tk func.expl.ret=long double
'tk func.expm1.arg.0=arithmetic,x
'tk func.expm1.args=1
'tk func.expm1.ret=floating_point
'tk func.expm1f.arg.0=float,x
'tk func.expm1f.args=1
'tk func.expm1f.ret=float
'tk func.expm1l.arg.0=long double,x
'tk func.expm1l.args=1
'tk func.expm1l.ret=long double
'tk func.fabs.arg.0=arithmetic,x
'tk func.fabs.args=1
'tk func.fabs.ret=floating_point
'tk func.fabsf.arg.0=float,x
'tk func.fabsf.args=1
'tk func.fabsf.ret=float
'tk func.fabsl.arg.0=long double,x
'tk func.fabsl.args=1
'tk func.fabsl.ret=long double
'tk func.fchmod.arg.0=int,fd
'tk func.fchmod.arg.1=int,mode
'tk func.fchmod.args=2
'tk func.fchmod.ret=int
'tk func.fclose.arg.0=FILE *,stream
'tk func.fclose.args=1
'tk func.fclose.ret=int
'tk func.fdim.arg.0=arithmetic,x
'tk func.fdim.arg.1=arithmetic,y
'tk func.fdim.args=2
'tk func.fdim.ret=floating_point
'tk func.fdimf.arg.0=float,x
'tk func.fdimf.arg.1=float,y
'tk func.fdimf.args=2
'tk func.fdimf.ret=float
'tk func.fdiml.arg.0=long double,x
'tk func.fdiml.arg.1=long double,y
'tk func.fdiml.args=2
'tk func.fdiml.ret=long double
'tk func.feclearexcept.arg.0=int,excepts
'tk func.feclearexcept.args=1
'tk func.feclearexcept.ret=int
'tk func.fegetenv.arg.0=fenv_t *,envp
'tk func.fegetenv.args=1
'tk func.fegetenv.ret=int
'tk func.fegetexceptflag.arg.0=fexcept_t *,flagp
'tk func.fegetexceptflag.arg.1=int,excepts
'tk func.fegetexceptflag.args=2
'tk func.fegetexceptflag.ret=int
'tk func.fegetround.args=0
'tk func.fegetround.ret=int
'tk func.feholdexcept.arg.0=fenv_t *,envp
'tk func.feholdexcept.args=1
'tk func.feholdexcept.ret=int
'tk func.feof.arg.0=FILE *,stream
'tk func.feof.args=1
'tk func.feof.ret=int
'tk func.feraiseexcept.arg.0=int,excepts
'tk func.feraiseexcept.args=1
'tk func.feraiseexcept.ret=int
'tk func.ferror.arg.0=FILE *,stream
'tk func.ferror.args=1
'tk func.ferror.ret=int
'tk func.fesetenv.arg.0=const,fenv_t*
'tk func.fesetenv.args=1
'tk func.fesetenv.ret=int
'tk func.fesetexceptflag.arg.0=const,fexcept_t*
'tk func.fesetexceptflag.arg.1=int,excepts
'tk func.fesetexceptflag.args=2
'tk func.fesetexceptflag.ret=int
'tk func.fesetround.arg.0=int,round
'tk func.fesetround.args=1
'tk func.fesetround.ret=int
'tk func.fetestexcept.arg.0=int,excepts
'tk func.fetestexcept.args=1
'tk func.fetestexcept.ret=int
'tk func.feupdateenv.arg.0=const,fenv_t*
'tk func.feupdateenv.args=1
'tk func.feupdateenv.ret=int
'tk func.fflagtostr.arg.0=int,flags
'tk func.fflagtostr.args=1
'tk func.fflagtostr.ret=char*
'tk func.fflush.arg.0=FILE *,stream
'tk func.fflush.args=1
'tk func.fflush.ret=int
'tk func.fflush_unlocked.arg.0=FILE *,stream
'tk func.fflush_unlocked.args=1
'tk func.fflush_unlocked.ret=int
'tk func.fgetc.arg.0=FILE *,stream
'tk func.fgetc.args=1
'tk func.fgetc.ret=int
'tk func.fgetpos.arg.0=FILE *,stream
'tk func.fgetpos.arg.1=fpos_t*,pos
'tk func.fgetpos.args=2
'tk func.fgetpos.ret=int
'tk func.fgets.arg.0=char *,s
'tk func.fgets.arg.1=int,size
'tk func.fgets.arg.2=FILE *,stream
'tk func.fgets.args=3
'tk func.fgets.ret=char *
'tk func.fgetwc.arg.0=FILE *,stream
'tk func.fgetwc.args=1
'tk func.fgetwc.ret=wint_t
'tk func.fgetws.arg.0=wchar_t *,s
'tk func.fgetws.arg.1=int,n
'tk func.fgetws.arg.2=FILE *,stream
'tk func.fgetws.args=3
'tk func.fgetws.ret=wchar_t*
'tk func.fileno.arg.0=FILE *,stream
'tk func.fileno.args=1
'tk func.fileno.ret=int
'tk func.floor.arg.0=arithmetic,x
'tk func.floor.args=1
'tk func.floor.ret=floating_point
'tk func.floorf.arg.0=float,x
'tk func.floorf.args=1
'tk func.floorf.ret=float
'tk func.floorl.arg.0=long double,x
'tk func.floorl.args=1
'tk func.floorl.ret=long double
'tk func.fma.arg.0=arithmetic,x
'tk func.fma.arg.1=arithmetic,y
'tk func.fma.arg.2=arithmetic,z
'tk func.fma.args=3
'tk func.fma.ret=floating_point
'tk func.fmaf.arg.0=float,x
'tk func.fmaf.arg.1=float,y
'tk func.fmaf.arg.2=float,z
'tk func.fmaf.args=3
'tk func.fmaf.ret=float
'tk func.fmal.arg.0=long double,x
'tk func.fmal.arg.1=long double,y
'tk func.fmal.arg.2=long double,z
'tk func.fmal.args=3
'tk func.fmal.ret=long double
'tk func.fmax.arg.0=arithmetic,x
'tk func.fmax.arg.1=arithmetic,y
'tk func.fmax.args=2
'tk func.fmax.ret=floating_point
'tk func.fmaxf.arg.0=float,x
'tk func.fmaxf.arg.1=float,y
'tk func.fmaxf.args=2
'tk func.fmaxf.ret=float
'tk func.fmaxl.arg.0=long double,x
'tk func.fmaxl.arg.1=long double,y
'tk func.fmaxl.args=2
'tk func.fmaxl.ret=long double
'tk func.fmin.arg.0=arithmetic,x
'tk func.fmin.arg.1=arithmetic,y
'tk func.fmin.args=2
'tk func.fmin.ret=floating_point
'tk func.fminf.arg.0=float,x
'tk func.fminf.arg.1=float,y
'tk func.fminf.args=2
'tk func.fminf.ret=float
'tk func.fminl.arg.0=long double,x
'tk func.fminl.arg.1=long double,y
'tk func.fminl.args=2
'tk func.fminl.ret=long double
'tk func.fmod.arg.0=arithmetic,x
'tk func.fmod.arg.1=arithmetic,y
'tk func.fmod.args=2
'tk func.fmod.ret=floating_point
'tk func.fmodf.arg.0=float,x
'tk func.fmodf.arg.1=float,y
'tk func.fmodf.args=2
'tk func.fmodf.ret=float
'tk func.fmodl.arg.0=long double,x
'tk func.fmodl.arg.1=long double,y
'tk func.fmodl.args=2
'tk func.fmodl.ret=long double
'tk func.fopen.arg.0=const char *,filename
'tk func.fopen.arg.1=const char *,mode
'tk func.fopen.args=2
'tk func.fopen.ret=file*
'tk func.fpclassify.arg.0=arithmetic,x
'tk func.fpclassify.args=1
'tk func.fpclassify.ret=int
'tk func.fprintf.arg.0=FILE *,stream
'tk func.fprintf.arg.1=const char *,format
'tk func.fprintf.arg.2= ,...
'tk func.fprintf.args=3
'tk func.fprintf.ret=int
'tk func.fputc.arg.0=int,c
'tk func.fputc.arg.1=FILE *,stream
'tk func.fputc.args=2
'tk func.fputc.ret=int
'tk func.fputs.arg.0=const char *,s
'tk func.fputs.arg.1=FILE *,stream
'tk func.fputs.args=2
'tk func.fputs.ret=int
'tk func.fputwc.arg.0=wchar_t,c
'tk func.fputwc.arg.1=FILE *,stream
'tk func.fputwc.args=2
'tk func.fputwc.ret=wint_t
'tk func.fputws.arg.0=const wchar_t *,s
'tk func.fputws.arg.1=FILE *,stream
'tk func.fputws.args=2
'tk func.fputws.ret=int
'tk func.fread.arg.0=void *,ptr
'tk func.fread.arg.1=size_t,size
'tk func.fread.arg.2=size_t,nmemb
'tk func.fread.arg.3=FILE *,stream
'tk func.fread.args=4
'tk func.fread.ret=size_t
'tk func.free.arg.0=void *,ptr
'tk func.free.args=1
'tk func.free.ret=void
'tk func.freopen.arg.0=const char *,filename
'tk func.freopen.arg.1=const char *,mode
'tk func.freopen.arg.2=FILE *,stream
'tk func.freopen.args=3
'tk func.freopen.ret=file*
'tk func.frexp.arg.0=arithmetic,value
'tk func.frexp.arg.1=int *,exp
'tk func.frexp.args=2
'tk func.frexp.ret=floating_point
'tk func.frexpf.arg.0=float,value
'tk func.frexpf.arg.1=int *,exp
'tk func.frexpf.args=2
'tk func.frexpf.ret=float
'tk func.frexpl.arg.0=long double,value
'tk func.frexpl.arg.1=int *,exp
'tk func.frexpl.args=2
'tk func.frexpl.ret=long double
'tk func.fscanf.arg.0=FILE *,stream
'tk func.fscanf.arg.1=const char *,format
'tk func.fscanf.arg.2=,...
'tk func.fscanf.args=3
'tk func.fscanf.ret=int
'tk func.fseek.arg.0=FILE *,stream
'tk func.fseek.arg.1=long,offset
'tk func.fseek.arg.2=int,whence
'tk func.fseek.args=3
'tk func.fseek.ret=int
'tk func.fsetpos.arg.0=FILE *,stream
'tk func.fsetpos.arg.1=const fpos_t*,pos
'tk func.fsetpos.args=2
'tk func.fsetpos.ret=int
'tk func.fstat.arg.0=int,fildes
'tk func.fstat.arg.1=void *,buf
'tk func.fstat.args=2
'tk func.fstat.ret=int
'tk func.ftell.arg.0=FILE *,stream
'tk func.ftell.args=1
'tk func.ftell.ret=long
'tk func.fts_children_INODE64.arg.0=void*,ftsp
'tk func.fts_children_INODE64.arg.1=int,opotions
'tk func.fts_children_INODE64.args=2
'tk func.fts_children_INODE64.ret=void *
'tk func.fts_close_INODE64.arg.0=void*,ftsp
'tk func.fts_close_INODE64.args=1
'tk func.fts_close_INODE64.ret=int
'tk func.fts_open_INODE64.arg.0=const char *,path_argv
'tk func.fts_open_INODE64.arg.1=int,options
'tk func.fts_open_INODE64.arg.2=void *,compar
'tk func.fts_open_INODE64.arg.3=void *,ftsen$INODE64t
'tk func.fts_open_INODE64.args=4
'tk func.fts_open_INODE64.ret=void *
'tk func.fts_read_INODE64.arg.0=void*,ftsp
'tk func.fts_read_INODE64.args=1
'tk func.fts_read_INODE64.ret=void *
'tk func.fts_set_INODE64.arg.0=void*,ftsp
'tk func.fts_set_INODE64.arg.1=void*,f
'tk func.fts_set_INODE64.arg.2=int,options
'tk func.fts_set_INODE64.args=3
'tk func.fts_set_INODE64.ret=int
'tk func.fwide.arg.0=FILE *,stream
'tk func.fwide.arg.1=int,mode
'tk func.fwide.args=2
'tk func.fwide.ret=int
'tk func.fwprintf.arg.0=FILE *,stream
'tk func.fwprintf.arg.1=const wchar_t *,format
'tk func.fwprintf.args=2
'tk func.fwprintf.ret=int
'tk func.fwrite.arg.0=const void *,ptr
'tk func.fwrite.arg.1=size_t,size
'tk func.fwrite.arg.2=size_t,nitems
'tk func.fwrite.arg.3=FILE *,stream
'tk func.fwrite.args=4
'tk func.fwrite.ret=size_t
'tk func.fwscanf.arg.0=FILE *,stream
'tk func.fwscanf.arg.1=const wchar_t *,format
'tk func.fwscanf.args=2
'tk func.fwscanf.ret=int
'tk func.getbsize.arg.0=int *,hdrlenp
'tk func.getbsize.arg.1=int *,bsizep
'tk func.getbsize.args=2
'tk func.getbsize.ret=char *
'tk func.getc.arg.0=FILE *,stream
'tk func.getc.args=1
'tk func.getc.ret=int
'tk func.getchar.args=0
'tk func.getchar.ret=int
'tk func.getenv.arg.0=const char *,name
'tk func.getenv.args=1
'tk func.getenv.ret=char *
'tk func.geteuid.args=0
'tk func.geteuid.ret=uid_t
'tk func.getopt.arg.0=int,argc
'tk func.getopt.arg.1=const char * *,argv
'tk func.getopt.arg.2=const char *,optstring
'tk func.getopt.args=3
'tk func.getopt.ret=int
'tk func.getopt_long.arg.0=int,argc
'tk func.getopt_long.arg.1=char **,argv
'tk func.getopt_long.arg.2=const char*,optstring
'tk func.getopt_long.arg.3=void *,longopts
'tk func.getopt_long.arg.4=int,longidx
'tk func.getopt_long.args=5
'tk func.getopt_long.ret=int
'tk func.getpid.args=0
'tk func.getpid.ret=int
'tk func.getprogname.args=0
'tk func.getprogname.ret=const char *
'tk func.gets.arg.0=char *,s
'tk func.gets.args=1
'tk func.gets.ret=char *
'tk func.getsockname.arg.0=int,sockfd
'tk func.getsockname.arg.1=struct sockaddr *,addr
'tk func.getsockname.arg.2=socklen_t *,addrlen
'tk func.getsockname.args=3
'tk func.getsockname.ret=int
'tk func.getsockopt.arg.0=int,sockfd
'tk func.getsockopt.arg.1=int,level
'tk func.getsockopt.arg.2=int,optname
'tk func.getsockopt.arg.3=void *,optval
'tk func.getsockopt.arg.4=socklen_t *,optlen
'tk func.getsockopt.args=5
'tk func.getsockopt.ret=int
'tk func.getuid.args=0
'tk func.getuid.ret=uid_t
'tk func.getwc.arg.0=FILE *,stream
'tk func.getwc.args=1
'tk func.getwc.ret=wint_t
'tk func.getwchar.args=0
'tk func.getwchar.ret=wint_t
'tk func.gmtime.arg.0=const time_t *,timer
'tk func.gmtime.args=1
'tk func.gmtime.ret=tm*
'tk func.group_from_gid.arg.0=gid_t,gid
'tk func.group_from_gid.arg.1=int,nogroup
'tk func.group_from_gid.args=2
'tk func.group_from_gid.ret=char *
'tk func.group_from_uid.include=grp.h
'tk func.humanize_number.arg.0=char *,buf
'tk func.humanize_number.arg.1=size_t,len
'tk func.humanize_number.arg.2=int64_t,number
'tk func.humanize_number.arg.3=const char *,suffix
'tk func.humanize_number.arg.4=int,scale
'tk func.humanize_number.arg.5=int,flags
'tk func.humanize_number.args=1
'tk func.humanize_number.ret=int
'tk func.hypot.arg.0=arithmetic,x
'tk func.hypot.arg.1=arithmetic,y
'tk func.hypot.args=2
'tk func.hypot.ret=floating_point
'tk func.hypotf.arg.0=float,x
'tk func.hypotf.arg.1=float,y
'tk func.hypotf.args=2
'tk func.hypotf.ret=float
'tk func.hypotl.arg.0=long double,x
'tk func.hypotl.arg.1=long double,y
'tk func.hypotl.args=2
'tk func.hypotl.ret=long double
'tk func.ilogb.arg.0=arithmetic,x
'tk func.ilogb.args=1
'tk func.ilogb.ret=int
'tk func.ilogbf.arg.0=float,x
'tk func.ilogbf.args=1
'tk func.ilogbf.ret=int
'tk func.ilogbl.arg.0=long double,x
'tk func.ilogbl.args=1
'tk func.ilogbl.ret=int
'tk func.imaxabs.arg.0=intmax_t,j
'tk func.imaxabs.args=1
'tk func.imaxabs.ret=intmax_t
'tk func.imaxdiv.arg.0=intmax_t,numer
'tk func.imaxdiv.arg.1=intmax_t,denom
'tk func.imaxdiv.args=2
'tk func.imaxdiv.ret=imaxdiv_t
'tk func.inet_aton.arg.0=const char *,cp
'tk func.inet_aton.arg.1=void *,pin
'tk func.inet_aton.args=2
'tk func.inet_aton.ret=int
'tk func.inet_ntoa.arg.0=void *,in
'tk func.inet_ntoa.args=1
'tk func.inet_ntoa.ret=char *
'tk func.initstate.arg.0=uint32_t,seed
'tk func.initstate.arg.1=char *,state
'tk func.initstate.arg.2=size_t,size
'tk func.initstate.args=3
'tk func.initstate.ret=char *
'tk func.ioctl.arg.0=int,fd
'tk func.ioctl.arg.1=unsigned long,request
'tk func.ioctl.args=2
'tk func.ioctl.ret=int
'tk func.isalnum.arg.0=int,c
'tk func.isalnum.args=1
'tk func.isalnum.ret=int
'tk func.isalpha.arg.0=int,c
'tk func.isalpha.args=1
'tk func.isalpha.ret=int
'tk func.isatty.arg.0=int,fd
'tk func.isatty.args=1
'tk func.isatty.ret=int
'tk func.isblank.arg.0=int,c
'tk func.isblank.args=1
'tk func.isblank.ret=int
'tk func.iscntrl.arg.0=int,c
'tk func.iscntrl.args=1
'tk func.iscntrl.ret=int
'tk func.isdigit.arg.0=int,c
'tk func.isdigit.args=1
'tk func.isdigit.ret=int
'tk func.isfinite.arg.0=arithmetic,x
'tk func.isfinite.args=1
'tk func.isfinite.ret=bool
'tk func.isgraph.arg.0=int,c
'tk func.isgraph.args=1
'tk func.isgraph.ret=int
'tk func.isgreater.arg.0=arithmetic,x
'tk func.isgreater.arg.1=arithmetic,y
'tk func.isgreater.args=2
'tk func.isgreater.ret=bool
'tk func.isgreaterequal.arg.0=arithmetic,x
'tk func.isgreaterequal.arg.1=arithmetic,y
'tk func.isgreaterequal.args=2
'tk func.isgreaterequal.ret=bool
'tk func.isinf.arg.0=arithmetic,x
'tk func.isinf.args=1
'tk func.isinf.ret=bool
'tk func.isless.arg.0=arithmetic,x
'tk func.isless.arg.1=arithmetic,y
'tk func.isless.args=2
'tk func.isless.ret=bool
'tk func.islessequal.arg.0=arithmetic,x
'tk func.islessequal.arg.1=arithmetic,y
'tk func.islessequal.args=2
'tk func.islessequal.ret=bool
'tk func.islessgreater.arg.0=arithmetic,x
'tk func.islessgreater.arg.1=arithmetic,y
'tk func.islessgreater.args=2
'tk func.islessgreater.ret=bool
'tk func.islower.arg.0=int,c
'tk func.islower.args=1
'tk func.islower.ret=int
'tk func.isnan.arg.0=arithmetic,x
'tk func.isnan.args=1
'tk func.isnan.ret=bool
'tk func.isnormal.arg.0=arithmetic,x
'tk func.isnormal.args=1
'tk func.isnormal.ret=bool
'tk func.isprint.arg.0=int,c
'tk func.isprint.args=1
'tk func.isprint.ret=int
'tk func.ispunct.arg.0=int,c
'tk func.ispunct.args=1
'tk func.ispunct.ret=int
'tk func.isspace.arg.0=int,c
'tk func.isspace.args=1
'tk func.isspace.ret=int
'tk func.isunordered.arg.0=arithmetic,x
'tk func.isunordered.arg.1=arithmetic,y
'tk func.isunordered.args=2
'tk func.isunordered.ret=bool
'tk func.isupper.arg.0=int,c
'tk func.isupper.args=1
'tk func.isupper.ret=int
'tk func.iswalnum.arg.0=wint_t,wc
'tk func.iswalnum.args=1
'tk func.iswalnum.ret=int
'tk func.iswalpha.arg.0=wint_t,wc
'tk func.iswalpha.args=1
'tk func.iswalpha.ret=int
'tk func.iswblank.arg.0=wint_t,wc
'tk func.iswblank.args=1
'tk func.iswblank.ret=int
'tk func.iswcntrl.arg.0=wint_t,wc
'tk func.iswcntrl.args=1
'tk func.iswcntrl.ret=int
'tk func.iswctype.arg.0=wint_t,wc
'tk func.iswctype.arg.1=wctype_t,desc
'tk func.iswctype.args=2
'tk func.iswctype.ret=int
'tk func.iswdigit.arg.0=wint_t,wc
'tk func.iswdigit.args=1
'tk func.iswdigit.ret=int
'tk func.iswgraph.arg.0=wint_t,wc
'tk func.iswgraph.args=1
'tk func.iswgraph.ret=int
'tk func.iswlower.arg.0=wint_t,wc
'tk func.iswlower.args=1
'tk func.iswlower.ret=int
'tk func.iswprint.arg.0=wint_t,wc
'tk func.iswprint.args=1
'tk func.iswprint.ret=int
'tk func.iswpunct.arg.0=wint_t,wc
'tk func.iswpunct.args=1
'tk func.iswpunct.ret=int
'tk func.iswspace.arg.0=wint_t,wc
'tk func.iswspace.args=1
'tk func.iswspace.ret=int
'tk func.iswupper.arg.0=wint_t,wc
'tk func.iswupper.args=1
'tk func.iswupper.ret=int
'tk func.iswxdigit.arg.0=wint_t,wc
'tk func.iswxdigit.args=1
'tk func.iswxdigit.ret=int
'tk func.isxdigit.arg.0=int,c
'tk func.isxdigit.args=1
'tk func.isxdigit.ret=int
'tk func.kill.arg.0=pid_t,pid
'tk func.kill.arg.1=int,sig
'tk func.kill.args=2
'tk func.kill.ret=int
'tk func.labs.arg.0=long,j
'tk func.labs.args=1
'tk func.labs.ret=long
'tk func.ldexp.arg.0=arithmetic,value
'tk func.ldexp.arg.1=int,exp
'tk func.ldexp.args=2
'tk func.ldexp.ret=floating_point
'tk func.ldexpf.arg.0=float,value
'tk func.ldexpf.arg.1=int,exp
'tk func.ldexpf.args=2
'tk func.ldexpf.ret=float
'tk func.ldexpl.arg.0=long double,value
'tk func.ldexpl.arg.1=int,exp
'tk func.ldexpl.args=2
'tk func.ldexpl.ret=long double
'tk func.ldiv.arg.0=long,numer
'tk func.ldiv.arg.1=long,denom
'tk func.ldiv.args=2
'tk func.ldiv.ret=ldiv_t
'tk func.lgamma.arg.0=arithmetic,x
'tk func.lgamma.args=1
'tk func.lgamma.ret=floating_point
'tk func.lgammaf.arg.0=float,x
'tk func.lgammaf.args=1
'tk func.lgammaf.ret=float
'tk func.lgammal.arg.0=long double,x
'tk func.lgammal.args=1
'tk func.lgammal.ret=long double
'tk func.libc_init.arg.0=int,argc
'tk func.libc_init.arg.1=char **,argv
'tk func.libc_init.arg.2=char **,envp
'tk func.libc_init.args=3
'tk func.libc_init.noreturn=true
'tk func.libc_init.ret=void
'tk func.libc_init_array.args=0
'tk func.libc_init_array.ret=void
'tk func.libc_start_main.arg.0=func,main
'tk func.libc_start_main.arg.1=int,argc
'tk func.libc_start_main.arg.2=char **,ubp_av
'tk func.libc_start_main.arg.3=func,init
'tk func.libc_start_main.arg.4=func,fini
'tk func.libc_start_main.arg.5=func,rtld_fini
'tk func.libc_start_main.arg.6=void *,stack_end
'tk func.libc_start_main.args=7
'tk func.libc_start_main.noreturn=true
'tk func.libc_start_main.ret=int
'tk func.listxattr.arg.0=const char *,path
'tk func.listxattr.arg.1=char*,namebuf
'tk func.listxattr.arg.2=int,fsize
'tk func.listxattr.arg.3=int,options
'tk func.listxattr.args=4
'tk func.listxattr.ret=int
'tk func.llabs.arg.0=long long,j
'tk func.llabs.args=1
'tk func.llabs.ret=long long
'tk func.lldiv.arg.0=long long,numer
'tk func.lldiv.arg.1=long long,denom
'tk func.lldiv.args=2
'tk func.lldiv.ret=lldiv_t
'tk func.llrint.arg.0=arithmetic,x
'tk func.llrint.args=1
'tk func.llrint.ret=long long
'tk func.llrintf.arg.0=float,x
'tk func.llrintf.args=1
'tk func.llrintf.ret=long long
'tk func.llrintl.arg.0=long double,x
'tk func.llrintl.args=1
'tk func.llrintl.ret=long long
'tk func.llround.arg.0=arithmetic,x
'tk func.llround.args=1
'tk func.llround.ret=long long
'tk func.llroundf.arg.0=float,x
'tk func.llroundf.args=1
'tk func.llroundf.ret=long long
'tk func.llroundl.arg.0=long double,x
'tk func.llroundl.args=1
'tk func.llroundl.ret=long long
'tk func.localeconv.args=0
'tk func.localeconv.ret=lconv*
'tk func.localtime.arg.0=const time_t *,timer
'tk func.localtime.args=1
'tk func.localtime.ret=tm*
'tk func.log.arg.0=arithmetic,x
'tk func.log.args=1
'tk func.log.ret=floating_point
'tk func.log10.arg.0=arithmetic,x
'tk func.log10.args=1
'tk func.log10.ret=floating_point
'tk func.log10f.arg.0=float,x
'tk func.log10f.args=1
'tk func.log10f.ret=float
'tk func.log10l.arg.0=long double,x
'tk func.log10l.args=1
'tk func.log10l.ret=long double
'tk func.log1p.arg.0=arithmetic,x
'tk func.log1p.args=1
'tk func.log1p.ret=floating_point
'tk func.log1pf.arg.0=float,x
'tk func.log1pf.args=1
'tk func.log1pf.ret=float
'tk func.log1pl.arg.0=long double,x
'tk func.log1pl.args=1
'tk func.log1pl.ret=long double
'tk func.log2.arg.0=arithmetic,x
'tk func.log2.args=1
'tk func.log2.ret=floating_point
'tk func.log2f.arg.0=float,x
'tk func.log2f.args=1
'tk func.log2f.ret=float
'tk func.log2l.arg.0=long double,x
'tk func.log2l.args=1
'tk func.log2l.ret=long double
'tk func.logb.arg.0=arithmetic,x
'tk func.logb.args=1
'tk func.logb.ret=floating_point
'tk func.logbf.arg.0=float,x
'tk func.logbf.args=1
'tk func.logbf.ret=float
'tk func.logbl.arg.0=long double,x
'tk func.logbl.args=1
'tk func.logbl.ret=long double
'tk func.logf.arg.0=float,x
'tk func.logf.args=1
'tk func.logf.ret=float
'tk func.logl.arg.0=long double,x
'tk func.logl.args=1
'tk func.logl.ret=long double
'tk func.longjmp.arg.0=jmp_buf,env
'tk func.longjmp.arg.1=int,val
'tk func.longjmp.args=2
'tk func.longjmp.ret=void
'tk func.lrint.arg.0=arithmetic,x
'tk func.lrint.args=1
'tk func.lrint.ret=long
'tk func.lrintf.arg.0=float,x
'tk func.lrintf.args=1
'tk func.lrintf.ret=long
'tk func.lrintl.arg.0=long double,x
'tk func.lrintl.args=1
'tk func.lrintl.ret=long
'tk func.lround.arg.0=arithmetic,x
'tk func.lround.args=1
'tk func.lround.ret=long
'tk func.lroundf.arg.0=float,x
'tk func.lroundf.args=1
'tk func.lroundf.ret=long
'tk func.lroundl.arg.0=long double,x
'tk func.lroundl.args=1
'tk func.lroundl.ret=long
'tk func.lstat.arg.0=const char *,path
'tk func.lstat.arg.1=void *,buf
'tk func.lstat.args=2
'tk func.lstat.ret=void
'tk func.main.arg.0=int,argc
'tk func.main.arg.1=char **,argv
'tk func.main.arg.2=char **,envp
'tk func.main.args=3
'tk func.main.ret=int
'tk func.malloc.arg.0=size_t,size
'tk func.malloc.args=1
'tk func.malloc.ret= void *
'tk func.maskrune.arg.0=uint32_t,c
'tk func.maskrune.arg.1=unsigned long,f
'tk func.maskrune.args=2
'tk func.maskrune.ret=int
'tk func.mblen.arg.0=const char *,s
'tk func.mblen.arg.1=size_t,n
'tk func.mblen.args=2
'tk func.mblen.ret=int
'tk func.mbrlen.arg.0=const char *,s
'tk func.mbrlen.arg.1=size_t,n
'tk func.mbrlen.arg.2=mbstate_t *,ps
'tk func.mbrlen.args=3
'tk func.mbrlen.ret=size_t
'tk func.mbrtowc.arg.0=wchar_t *,pwc
'tk func.mbrtowc.arg.1=const char *,s
'tk func.mbrtowc.arg.2=size_t,n
'tk func.mbrtowc.arg.3=mbstate_t *,ps
'tk func.mbrtowc.args=4
'tk func.mbrtowc.ret=size_t
'tk func.mbsinit.arg.0=const mbstate_t *,ps
'tk func.mbsinit.args=1
'tk func.mbsinit.ret=int
'tk func.mbsrtowcs.arg.0=wchar_t *,dst
'tk func.mbsrtowcs.arg.1=const char * *,src
'tk func.mbsrtowcs.arg.2=size_t,len
'tk func.mbsrtowcs.arg.3=mbstate_t *,ps
'tk func.mbsrtowcs.args=4
'tk func.mbsrtowcs.ret=size_t
'tk func.mbstowcs.arg.0=wchar_t *,pwcs
'tk func.mbstowcs.arg.1=const char *,s
'tk func.mbstowcs.arg.2=size_t,n
'tk func.mbstowcs.args=3
'tk func.mbstowcs.ret=size_t
'tk func.mbtowc.arg.0=wchar_t *,pwc
'tk func.mbtowc.arg.1=const char *,s
'tk func.mbtowc.arg.2=size_t,n
'tk func.mbtowc.args=3
'tk func.mbtowc.ret=int
'tk func.memchr.arg.0=void *,s
'tk func.memchr.arg.1=int,c
'tk func.memchr.arg.2=size_t,n
'tk func.memchr.args=3
'tk func.memchr.ret=void *
'tk func.memcmp.arg.0=const void *,s1
'tk func.memcmp.arg.1=const void *,s2
'tk func.memcmp.arg.2=size_t,n
'tk func.memcmp.args=3
'tk func.memcmp.ret=int
'tk func.memcpy.arg.0=void *,s1
'tk func.memcpy.arg.1=const void *,s2
'tk func.memcpy.arg.2=size_t,n
'tk func.memcpy.args=3
'tk func.memcpy.ret=void *
'tk func.memmem.arg.0=const void *,big
'tk func.memmem.arg.1=int,big_len
'tk func.memmem.arg.2=const void *,little
'tk func.memmem.arg.3=int,little_len
'tk func.memmem.args=4
'tk func.memmem.ret=void *
'tk func.memmove.arg.0=void *,s1
'tk func.memmove.arg.1=const void *,s2
'tk func.memmove.arg.2=size_t,n
'tk func.memmove.args=3
'tk func.memmove.ret=void *
'tk func.memset.arg.0=void *,s
'tk func.memset.arg.1=int,c
'tk func.memset.arg.2=size_t,n
'tk func.memset.args=3
'tk func.memset.ret=void *
'tk func.mkstemp.arg.0=char *,template
'tk func.mkstemp.args=1
'tk func.mkstemp.ret=int
'tk func.mktemp.arg.0=char *,template
'tk func.mktemp.args=1
'tk func.mktemp.ret=char *
'tk func.mktime.arg.0=tm *,timeptr
'tk func.mktime.args=1
'tk func.mktime.ret=time_t
'tk func.mmap.arg.0=void*,addr
'tk func.mmap.arg.1=size_t,length
'tk func.mmap.arg.2=int,prot
'tk func.mmap.arg.3=int,flags
'tk func.mmap.arg.4=int,fd
'tk func.mmap.arg.5=size_t,offset
'tk func.mmap.args=6
'tk func.mmap.ret=void*
'tk func.modf.arg.0=floating_point,value
'tk func.modf.arg.1=floating_point *,iptr
'tk func.modf.args=2
'tk func.modf.ret=floating_point
'tk func.modff.arg.0=float,value
'tk func.modff.arg.1=float *,iptr
'tk func.modff.args=2
'tk func.modff.ret=float
'tk func.modfl.arg.0=long double,value
'tk func.modfl.arg.1=long double *,iptr
'tk func.modfl.args=2
'tk func.modfl.ret=long double
'tk func.munmap.arg.0=void*,addr
'tk func.munmap.arg.1=size_t,length
'tk func.munmap.args=2
'tk func.munmap.ret=int
'tk func.nan.arg.0=const char *,str
'tk func.nan.args=1
'tk func.nan.ret=double
'tk func.nanf.arg.0=const char *,str
'tk func.nanf.args=1
'tk func.nanf.ret=float
'tk func.nanl.arg.0=const char *,str
'tk func.nanl.args=1
'tk func.nanl.ret=long double
'tk func.nanosleep.arg.0=const struct timespec *,req
'tk func.nanosleep.arg.1=struct timespec *,rem
'tk func.nanosleep.args=2
'tk func.nanosleep.ret=int
'tk func.nearbyint.arg.0=arithmetic,x
'tk func.nearbyint.args=1
'tk func.nearbyint.ret=floating_point
'tk func.nearbyintf.arg.0=float,x
'tk func.nearbyintf.args=1
'tk func.nearbyintf.ret=float
'tk func.nearbyintl.arg.0=long double,x
'tk func.nearbyintl.args=1
'tk func.nearbyintl.ret=long double
'tk func.nextafter.arg.0=arithmetic,x
'tk func.nextafter.arg.1=arithmetic,y
'tk func.nextafter.args=2
'tk func.nextafter.ret=floating_point
'tk func.nextafterf.arg.0=float,x
'tk func.nextafterf.arg.1=float,y
'tk func.nextafterf.args=2
'tk func.nextafterf.ret=float
'tk func.nextafterl.arg.0=long double,x
'tk func.nextafterl.arg.1=long double,y
'tk func.nextafterl.args=2
'tk func.nextafterl.ret=long double
'tk func.nexttoward.arg.0=arithmetic,x
'tk func.nexttoward.arg.1=long double,y
'tk func.nexttoward.args=2
'tk func.nexttoward.ret=floating_point
'tk func.nexttowardf.arg.0=float,x
'tk func.nexttowardf.arg.1=long double,y
'tk func.nexttowardf.args=2
'tk func.nexttowardf.ret=float
'tk func.nexttowardl.arg.0=long double,x
'tk func.nexttowardl.arg.1=long double,y
'tk func.nexttowardl.args=2
'tk func.nexttowardl.ret=long double
'tk func.nl_langinfo.arg.0=nl_item,item
'tk func.nl_langinfo.args=1
'tk func.nl_langinfo.ret=char *
'tk func.nl_langinfo_l.arg.0=nl_item,item
'tk func.nl_langinfo_l.arg.1=locale_t locale
'tk func.nl_langinfo_l.args=2
'tk func.nl_langinfo_l.ret=char *
'tk func.objc_allocWithZone.arg.0=void *
'tk func.objc_allocWithZone.args=1
'tk func.objc_allocWithZone.ret=void *
'tk func.objc_enumerationMutation.arg.0=void *,instance
'tk func.objc_enumerationMutation.args=1
'tk func.objc_enumerationMutation.ret=void
'tk func.objc_msgSend.arg.0=void *,instance
'tk func.objc_msgSend.arg.1=char *,selector
'tk func.objc_msgSend.args=2
'tk func.objc_msgSend.ret=void *
'tk func.objc_msgSendSuper2.arg.0=void *,instance
'tk func.objc_msgSendSuper2.arg.1=char *,selector
'tk func.objc_msgSendSuper2.args=2
'tk func.objc_msgSendSuper2.ret=void *
'tk func.objc_opt_self.arg.0=void *
'tk func.objc_opt_self.args=1
'tk func.objc_opt_self.ret=void *
'tk func.objc_release.arg.0=void *,instance
'tk func.objc_release.args=1
'tk func.objc_release.ret=void
'tk func.objc_retain.arg.0=void *,instance
'tk func.objc_retain.args=1
'tk func.objc_retain.ret=void
'tk func.objc_retainAutoreleasedReturnValue.arg.0=void *,instance
'tk func.objc_retainAutoreleasedReturnValue.args=1
'tk func.objc_retainAutoreleasedReturnValue.ret=void
'tk func.objc_storeStrong.arg.0=void *,instance
'tk func.objc_storeStrong.arg.1=int,type
'tk func.objc_storeStrong.args=2
'tk func.objc_storeStrong.ret=void *
'tk func.open.arg.0=const char *,path
'tk func.open.arg.1=int,oflag
'tk func.open.args=2
'tk func.open.ret=int
'tk func.openat.arg.0=int,fd
'tk func.openat.arg.1=const char *,path
'tk func.openat.arg.2=int,oflag
'tk func.openat.args=3
'tk func.openat.ret=int
'tk func.pclose.arg.0=FILE *,stream
'tk func.pclose.args=1
'tk func.pclose.ret=int
'tk func.perror.arg.0=const char *,s
'tk func.perror.args=1
'tk func.perror.ret=void
'tk func.popen.arg.0=const char *,filename
'tk func.popen.arg.1=const char *,mode
'tk func.popen.args=2
'tk func.popen.ret=file*
'tk func.pow.arg.0=arithmetic,x
'tk func.pow.arg.1=arithmetic,y
'tk func.pow.args=2
'tk func.pow.ret=floating_point
'tk func.powf.arg.0=float,x
'tk func.powf.arg.1=float,y
'tk func.powf.args=2
'tk func.powf.ret=float
'tk func.powl.arg.0=long double,x
'tk func.powl.arg.1=long double,y
'tk func.powl.args=2
'tk func.powl.ret=long double
'tk func.prctl.arg.0=int,option
'tk func.prctl.arg.1=unsigned long,v2
'tk func.prctl.arg.2=unsigned long,v3
'tk func.prctl.arg.3=unsigned long,v4
'tk func.prctl.arg.4=unsigned long,v5
'tk func.prctl.args=5
'tk func.prctl.ret=int
'tk func.printf.arg.0=const char *,format
'tk func.printf.args=1
'tk func.printf.ret=int
'tk func.ptrace.arg.0=__ptrace_request,request
'tk func.ptrace.arg.1=pid_t,pid
'tk func.ptrace.arg.2=void*,addr
'tk func.ptrace.arg.3=void*,data
'tk func.ptrace.args=4
'tk func.ptrace.ret=long
'tk func.putc.arg.0=int,c
'tk func.putc.arg.1=FILE *,stream
'tk func.putc.args=2
'tk func.putc.ret=int
'tk func.putchar.arg.0=int,c
'tk func.putchar.args=1
'tk func.putchar.ret=int
'tk func.puts.arg.0=const char *,s
'tk func.puts.args=1
'tk func.puts.ret=int
'tk func.pututxline.arg.0=void *,utx
'tk func.pututxline.args=1
'tk func.pututxline.ret=void *
'tk func.putwc.arg.0=wchar_t,c
'tk func.putwc.arg.1=FILE *,stream
'tk func.putwc.args=2
'tk func.putwc.ret=wint_t
'tk func.putwchar.arg.0=wchar_t,c
'tk func.putwchar.args=1
'tk func.putwchar.ret=wint_t
'tk func.qsort.arg.0=void *,base
'tk func.qsort.arg.1=size_t,nmemb
'tk func.qsort.arg.2=size_t,size
'tk func.qsort.arg.3=int(*compar)(const void *,const void *)
'tk func.qsort.args=4
'tk func.quick_exit.arg.0=int,status
'tk func.quick_exit.args=1
'tk func.quick_exit.ret=void
'tk func.raise.arg.0=int,sig
'tk func.raise.args=1
'tk func.raise.ret=int
'tk func.rand.args=0
'tk func.rand.ret=int
'tk func.random.args=0
'tk func.random.ret=uint32_t
'tk func.read.arg.0=int,fildes
'tk func.read.arg.1=void *,buf
'tk func.read.arg.2=size_t,nbyte
'tk func.read.args=3
'tk func.read.ret=ssize_t
'tk func.readlink.arg.0=const char *,path
'tk func.readlink.arg.1=char *,buf
'tk func.readlink.arg.2=int,bufsize
'tk func.readlink.args=3
'tk func.readlink.ret=int
'tk func.realloc.arg.0=void *,ptr
'tk func.realloc.arg.1=size_t,size
'tk func.realloc.args=2
'tk func.realloc.ret=void *
'tk func.reallocf.arg.0=void *,ptr
'tk func.reallocf.arg.1=size_t,size
'tk func.reallocf.args=2
'tk func.reallocf.ret=void *
'tk func.recv.arg.0=int,socket
'tk func.recv.arg.1=void *,buffer
'tk func.recv.arg.2=size_t,length
'tk func.recv.arg.3=int,flags
'tk func.recv.args=4
'tk func.recv.ret=ssize_t
'tk func.recvfrom.arg.0=int,socket
'tk func.recvfrom.arg.1=void *,buffer
'tk func.recvfrom.arg.2=size_t,length
'tk func.recvfrom.arg.3=int,flags
'tk func.recvfrom.args=4
'tk func.recvfrom.ret=ssize_t
'tk func.remainder.arg.0=arithmetic,x
'tk func.remainder.arg.1=arithmetic,y
'tk func.remainder.args=2
'tk func.remainder.ret=floating_point
'tk func.remainderf.arg.0=float,x
'tk func.remainderf.arg.1=float,y
'tk func.remainderf.args=2
'tk func.remainderf.ret=float
'tk func.remainderl.arg.0=long double,x
'tk func.remainderl.arg.1=long double,y
'tk func.remainderl.args=2
'tk func.remainderl.ret=long double
'tk func.remove.arg.0=const char *,filename
'tk func.remove.args=1
'tk func.remove.ret=int
'tk func.remquo.arg.0=arithmetic,x
'tk func.remquo.arg.1=arithmetic,y
'tk func.remquo.arg.2=int *,pquo
'tk func.remquo.args=3
'tk func.remquo.ret=floating_point
'tk func.remquof.arg.0=float,x
'tk func.remquof.arg.1=float,y
'tk func.remquof.arg.2=int *,pquo
'tk func.remquof.args=3
'tk func.remquof.ret=float
'tk func.remquol.arg.0=long double,x
'tk func.remquol.arg.1=long double,y
'tk func.remquol.arg.2=int *,pquo
'tk func.remquol.args=3
'tk func.remquol.ret=long double
'tk func.rename.arg.0=const char *,oldpath
'tk func.rename.arg.1=const char *,newpath
'tk func.rename.args=2
'tk func.rename.ret=int
'tk func.rewind.arg.0=FILE *,stream
'tk func.rewind.args=1
'tk func.rewind.ret=void
'tk func.rint.arg.0=arithmetic,x
'tk func.rint.args=1
'tk func.rint.ret=floating_point
'tk func.rintf.arg.0=float,x
'tk func.rintf.args=1
'tk func.rintf.ret=float
'tk func.rintl.arg.0=long double,x
'tk func.rintl.args=1
'tk func.rintl.ret=long double
'tk func.round.arg.0=arithmetic,x
'tk func.round.args=1
'tk func.round.ret=floating_point
'tk func.roundf.arg.0=float,x
'tk func.roundf.args=1
'tk func.roundf.ret=float
'tk func.roundl.arg.0=long double,x
'tk func.roundl.args=1
'tk func.roundl.ret=long double
'tk func.scalbln.arg.0=arithmetic,x
'tk func.scalbln.arg.1=long,ex
'tk func.scalbln.args=2
'tk func.scalbln.ret=floating_point
'tk func.scalblnf.arg.0=float,x
'tk func.scalblnf.arg.1=long,ex
'tk func.scalblnf.args=2
'tk func.scalblnf.ret=float
'tk func.scalblnl.arg.0=long double,x
'tk func.scalblnl.arg.1=long,ex
'tk func.scalblnl.args=2
'tk func.scalblnl.ret=long double
'tk func.scalbn.arg.0=arithmetic,x
'tk func.scalbn.arg.1=int,ex
'tk func.scalbn.args=2
'tk func.scalbn.ret=floating_point
'tk func.scalbnf.arg.0=float,x
'tk func.scalbnf.arg.1=int,ex
'tk func.scalbnf.args=2
'tk func.scalbnf.ret=float
'tk func.scalbnl.arg.0=long double,x
'tk func.scalbnl.arg.1=int,ex
'tk func.scalbnl.args=2
'tk func.scalbnl.ret=long double
'tk func.scanf.arg.0=const char *,format
'tk func.scanf.arg.1=,...
'tk func.scanf.args=2
'tk func.scanf.ret=int
'tk func.select.arg.0=int,nfds
'tk func.select.arg.1=fd_set *,readfds
'tk func.select.arg.2=fd_set *,writefds
'tk func.select.arg.3=fd_set *,exceptfds
'tk func.select.arg.4=struct timeval *,timeout
'tk func.select.args=5
'tk func.select.ret=int
'tk func.send.arg.0=int,socket
'tk func.send.arg.1=void *,buffer
'tk func.send.arg.2=size_t,length
'tk func.send.arg.3=int,flags
'tk func.send.args=4
'tk func.send.ret=ssize_t
'tk func.setbuf.arg.0=FILE *,stream
'tk func.setbuf.arg.1=char *,buf
'tk func.setbuf.args=2
'tk func.setbuf.ret=void
'tk func.setenv.arg.0=const char *,name
'tk func.setenv.arg.1=const char *,value
'tk func.setenv.arg.2=int,overwrite
'tk func.setenv.args=3
'tk func.setenv.ret=int
'tk func.setgid.arg.0=int,gid
'tk func.setgid.args=1
'tk func.setgid.ret=int
'tk func.setjmp.arg.0=jmpbuf,env
'tk func.setjmp.args=1
'tk func.setjmp.ret=int
'tk func.setlocale.arg.0=int,category
'tk func.setlocale.arg.1=const char *,locale
'tk func.setlocale.args=2
'tk func.setlocale.ret=char *
'tk func.setsockopt.arg.0=int,sockfd
'tk func.setsockopt.arg.1=int,level
'tk func.setsockopt.arg.2=int,optname
'tk func.setsockopt.arg.3=void *,optval
'tk func.setsockopt.arg.4=socklen_t,optlen
'tk func.setsockopt.args=5
'tk func.setsockopt.ret=int
'tk func.setstate.arg.0=const char *,state
'tk func.setstate.args=1
'tk func.setstate.ret=const char *
'tk func.setuid.arg.0=int,uid
'tk func.setuid.args=1
'tk func.setuid.ret=int
'tk func.setvbuf.arg.0=FILE*,stream
'tk func.setvbuf.arg.1=char *,buf
'tk func.setvbuf.arg.2=int,mode
'tk func.setvbuf.arg.3=size_t,size
'tk func.setvbuf.args=4
'tk func.setvbuf.ret=int
'tk func.sigaction.arg.0=int,signum
'tk func.sigaction.arg.1=const struct sigaction *,act
'tk func.sigaction.arg.2=struct sigaction *,oldact
'tk func.sigaction.args=3
'tk func.sigaction.ret=int
'tk func.signal.arg.0=int,sig
'tk func.signal.arg.1=void *,func
'tk func.signal.args=2
'tk func.signal.ret=void
'tk func.signbit.arg.0=arithmetic,x
'tk func.signbit.args=1
'tk func.signbit.ret=bool
'tk func.sigprocmask.arg.0=int,how
'tk func.sigprocmask.arg.1=void *,set
'tk func.sigprocmask.arg.2=void *,oldset
'tk func.sigprocmask.args=3
'tk func.sigprocmask.ret=pid_t
'tk func.sin.arg.0=arithmetic,x
'tk func.sin.args=1
'tk func.sin.ret=floating_point
'tk func.sinf.arg.0=float,x
'tk func.sinf.args=1
'tk func.sinf.ret=float
'tk func.sinh.arg.0=arithmetic,x
'tk func.sinh.args=1
'tk func.sinh.ret=floating_point
'tk func.sinhf.arg.0=float,x
'tk func.sinhf.args=1
'tk func.sinhf.ret=float
'tk func.sinhl.arg.0=long double,x
'tk func.sinhl.args=1
'tk func.sinhl.ret=long double
'tk func.sinl.arg.0=long double,x
'tk func.sinl.args=1
'tk func.sinl.ret=long double
'tk func.sleep.arg.0=int,s
'tk func.sleep.args=1
'tk func.sleep.ret=int
'tk func.snprintf.arg.0=char *,s
'tk func.snprintf.arg.1=size_t,size
'tk func.snprintf.arg.2=const char *,format
'tk func.snprintf.arg.3=,...
'tk func.snprintf.args=4
'tk func.snprintf.ret=int
'tk func.snprintf_chk.arg.0=char *,s
'tk func.snprintf_chk.arg.1=size_t,maxlen
'tk func.snprintf_chk.arg.2=int,flag
'tk func.snprintf_chk.arg.3=size_t,slen
'tk func.snprintf_chk.arg.4=const char *,format
'tk func.snprintf_chk.args=5
'tk func.snprintf_chk.ret=int
'tk func.socket.arg.0=int,domain
'tk func.socket.arg.1=int,type
'tk func.socket.arg.2=int,protocol
'tk func.socket.args=3
'tk func.socket.ret=int
'tk func.sprintf.arg.0=char *,s
'tk func.sprintf.arg.1=const char *,format
'tk func.sprintf.arg.2=,...
'tk func.sprintf.args=3
'tk func.sprintf.ret=int
'tk func.sprintf_chk.arg.0=char *,s
'tk func.sprintf_chk.arg.1=int,flag
'tk func.sprintf_chk.arg.2=size_t,slen
'tk func.sprintf_chk.arg.3=const char *,format
'tk func.sprintf_chk.args=4
'tk func.sprintf_chk.ret=int
'tk func.sqrt.arg.0=arithmetic,x
'tk func.sqrt.args=1
'tk func.sqrt.ret=floating_point
'tk func.sqrtf.arg.0=float,x
'tk func.sqrtf.args=1
'tk func.sqrtf.ret=float
'tk func.sqrtl.arg.0=long double,x
'tk func.sqrtl.args=1
'tk func.sqrtl.ret=long double
'tk func.srand.arg.0=int,seed
'tk func.srand.args=1
'tk func.srand.ret=void
'tk func.srandom.arg.0=uint32_t,seed
'tk func.srandom.args=1
'tk func.srandom.ret=uint32_t
'tk func.srandomdev.args=0
'tk func.srandomdev.ret=void
'tk func.sscanf.arg.0=const char *,s
'tk func.sscanf.arg.1=const char *,format
'tk func.sscanf.arg.2= ,...
'tk func.sscanf.args=3
'tk func.sscanf.ret=int
'tk func.stack_chk_fail.args=0
'tk func.stack_chk_fail.noreturn=true
'tk func.stack_chk_fail.ret=void
'tk func.strcasecmp.arg.0=const char *,s1
'tk func.strcasecmp.arg.1=const char *,s2
'tk func.strcasecmp.args=2
'tk func.strcasecmp.ret=int
'tk func.strcat.arg.0=char *,s1
'tk func.strcat.arg.1=const char *,s2
'tk func.strcat.args=2
'tk func.strcat.ret=char *
'tk func.strchr.arg.0=const char *,s
'tk func.strchr.arg.1=int,c
'tk func.strchr.args=2
'tk func.strchr.ret=char *
'tk func.strcmp.arg.0=const char *,s1
'tk func.strcmp.arg.1=const char *,s2
'tk func.strcmp.args=2
'tk func.strcmp.ret=int
'tk func.strcoll.arg.0=const char *,s1
'tk func.strcoll.arg.1=const char *,s2
'tk func.strcoll.args=2
'tk func.strcoll.ret=int
'tk func.strcpy.arg.0=char *,dest
'tk func.strcpy.arg.1=const char *,src
'tk func.strcpy.args=2
'tk func.strcpy.ret=char *
'tk func.strcpy_chk.arg.0=char *,dest
'tk func.strcpy_chk.arg.1=const char *,src
'tk func.strcpy_chk.arg.2=size_t,destlen
'tk func.strcpy_chk.args=3
'tk func.strcpy_chk.ret=char *
'tk func.strcspn.arg.0=const char *,s1
'tk func.strcspn.arg.1=const char *,s2
'tk func.strcspn.args=2
'tk func.strcspn.ret=size_t
'tk func.strdup.arg.0=const char *,src
'tk func.strdup.args=1
'tk func.strdup.ret=char *
'tk func.strerror.arg.0=int,errnum
'tk func.strerror.args=1
'tk func.strerror.ret=char *
'tk func.strftime.arg.0=char *,s
'tk func.strftime.arg.1=size_t,maxsize
'tk func.strftime.arg.2=const char *,format
'tk func.strftime.arg.3=const tm *,timeptr
'tk func.strftime.args=4
'tk func.strftime.ret=size_t
'tk func.strlcpy.arg.0=char *,dest
'tk func.strlcpy.arg.1=const char *,src
'tk func.strlcpy.arg.2=size_t, n
'tk func.strlcpy.args=3
'tk func.strlcpy.ret=char *
'tk func.strlen.arg.0=const char *,s
'tk func.strlen.args=1
'tk func.strlen.ret=size_t
'tk func.strmode.arg.0=int,mode
'tk func.strmode.arg.1=char *,bp
'tk func.strmode.args=2
'tk func.strmode.ret=void
'tk func.strncasecmp.arg.0=const char *,s1
'tk func.strncasecmp.arg.1=const char *,s2
'tk func.strncasecmp.arg.2=size_t,n
'tk func.strncasecmp.args=3
'tk func.strncasecmp.ret=int
'tk func.strncat.arg.0=char *,s1
'tk func.strncat.arg.1=const char *,s2
'tk func.strncat.arg.2=size_t,n
'tk func.strncat.args=3
'tk func.strncat.ret=char *
'tk func.strncmp.arg.0=const char *,s1
'tk func.strncmp.arg.1=const char *,s2
'tk func.strncmp.arg.2=size_t,n
'tk func.strncmp.args=3
'tk func.strncmp.ret=int
'tk func.strncpy.arg.0=char *,dest
'tk func.strncpy.arg.1=const char *,src
'tk func.strncpy.arg.2=size_t, n
'tk func.strncpy.args=3
'tk func.strncpy.ret=char *
'tk func.strndup.arg.0=const char *,src
'tk func.strndup.arg.1=int,n
'tk func.strndup.args=2
'tk func.strndup.ret=char *
'tk func.strpbrk.arg.0=const char *,s1
'tk func.strpbrk.arg.1=const char *,s2
'tk func.strpbrk.args=2
'tk func.strpbrk.ret=char *
'tk func.strrchr.arg.0=const char *,s
'tk func.strrchr.arg.1=int,c
'tk func.strrchr.args=2
'tk func.strrchr.ret=char *
'tk func.strspn.arg.0=const char *,s1
'tk func.strspn.arg.1=const char *,s2
'tk func.strspn.args=2
'tk func.strspn.ret=size_t
'tk func.strstr.arg.0=const char *,s1
'tk func.strstr.arg.1=const char *,s2
'tk func.strstr.args=2
'tk func.strstr.ret=char *
'tk func.strtod.arg.0=const char *,str
'tk func.strtod.arg.1=char * *,endptr
'tk func.strtod.args=2
'tk func.strtod.ret=double
'tk func.strtof.arg.0=const char *,str
'tk func.strtof.arg.1=char * *,endptr
'tk func.strtof.args=2
'tk func.strtof.ret=float
'tk func.strtoimax.arg.0=const char *,str
'tk func.strtoimax.arg.1=char * *,endptr
'tk func.strtoimax.arg.2=int,base
'tk func.strtoimax.args=3
'tk func.strtoimax.ret=intmax_t
'tk func.strtok.arg.0=char *,s1
'tk func.strtok.arg.1=const char *,s2
'tk func.strtok.args=2
'tk func.strtok.ret=char *
'tk func.strtol.arg.0=const char *,str
'tk func.strtol.arg.1=char * *,endptr
'tk func.strtol.arg.2=int,base
'tk func.strtol.args=3
'tk func.strtol.ret=long
'tk func.strtold.arg.0=const char *,str
'tk func.strtold.arg.1=char * *,endptr
'tk func.strtold.args=2
'tk func.strtold.ret=long double
'tk func.strtoll.arg.0=const char *,str
'tk func.strtoll.arg.1=char * *,endptr
'tk func.strtoll.arg.2=int,base
'tk func.strtoll.args=3
'tk func.strtoll.ret=long long
'tk func.strtonum.arg.0=const char *,str
'tk func.strtonum.arg.1=long long,minval
'tk func.strtonum.arg.2=long long,maxval
'tk func.strtonum.arg.3=const char **,errstr
'tk func.strtonum.args=4
'tk func.strtonum.ret=long long
'tk func.strtoul.arg.0=const char *,str
'tk func.strtoul.arg.1=char * *,endptr
'tk func.strtoul.arg.2=int,base
'tk func.strtoul.args=3
'tk func.strtoul.ret=long
'tk func.strtoull.arg.0=const char *,str
'tk func.strtoull.arg.1=char * *,endptr
'tk func.strtoull.arg.2=int,base
'tk func.strtoull.args=3
'tk func.strtoull.ret=long long
'tk func.strtoumax.arg.0=const char *,str
'tk func.strtoumax.arg.1=char * *,endptr
'tk func.strtoumax.arg.2=int,base
'tk func.strtoumax.args=3
'tk func.strtoumax.ret=uintmax_t
'tk func.strxfrm.arg.0=char *,s1
'tk func.strxfrm.arg.1=const char *,s2
'tk func.strxfrm.arg.2=size_t,n
'tk func.strxfrm.args=3
'tk func.strxfrm.ret=size_t
'tk func.swift_beginAccess.arg.0=void *
'tk func.swift_beginAccess.arg.1=void *
'tk func.swift_beginAccess.arg.2=void *
'tk func.swift_beginAccess.arg.3=void *
'tk func.swift_beginAccess.args=4
'tk func.swift_beginAccess.ret=void
'tk func.swift_bridgeObjectRelease.arg.0=void *
'tk func.swift_bridgeObjectRelease.args=1
'tk func.swift_bridgeObjectRelease.ret=void
'tk func.swift_bridgeObjectRetain.arg.0=void *
'tk func.swift_bridgeObjectRetain.args=1
'tk func.swift_bridgeObjectRetain.ret=void *
'tk func.swift_endAccess.arg.0=void *
'tk func.swift_endAccess.args=1
'tk func.swift_endAccess.ret=void
'tk func.swift_getObjCClassFromMetadata.arg.0=void *
'tk func.swift_getObjCClassFromMetadata.args=1
'tk func.swift_getObjCClassFromMetadata.ret=void *
'tk func.swift_initStackObject.arg.0=void *
'tk func.swift_initStackObject.arg.1=void *
'tk func.swift_initStackObject.args=2
'tk func.swift_initStackObject.ret=void *
'tk func.swift_release.arg.0=void *
'tk func.swift_release.args=1
'tk func.swift_release.ret=void
'tk func.swift_unexpectedError.arg.0=void *
'tk func.swift_unexpectedError.args=1
'tk func.swift_unexpectedError.ret=void
'tk func.swprintf.arg.0=wchar_t *,s
'tk func.swprintf.arg.1=size_t,n
'tk func.swprintf.arg.2=const wchar_t *,format
'tk func.swprintf.args=3
'tk func.swprintf.ret=int
'tk func.swscanf.arg.0=const wchar_t *,s
'tk func.swscanf.arg.1=const wchar_t *,format
'tk func.swscanf.args=2
'tk func.swscanf.ret=int
'tk func.symlink.arg.0=const char *,path1
'tk func.symlink.arg.1=const char *,path2
'tk func.symlink.args=2
'tk func.symlink.ret=int
'tk func.sysctl.arg.0=const char *,name
'tk func.sysctl.arg.1=int,namelen
'tk func.sysctl.arg.2=void *,oldp
'tk func.sysctl.arg.3=size_t *,oldlenp
'tk func.sysctl.arg.4=void *,newp
'tk func.sysctl.arg.5=size_t,newlen
'tk func.sysctl.args=6
'tk func.sysctl.ret=int
'tk func.sysctlbyname.arg.0=const char *,name
'tk func.sysctlbyname.arg.1=void *,oldp
'tk func.sysctlbyname.arg.2=size_t *,oldlenp
'tk func.sysctlbyname.arg.3=void *,newp
'tk func.sysctlbyname.arg.4=size_t,newlen
'tk func.sysctlbyname.args=5
'tk func.sysctlbyname.ret=int
'tk func.sysctlnametomib.arg.0=const char *,name
'tk func.sysctlnametomib.arg.1=int *,mib
'tk func.sysctlnametomib.arg.2=size_t *,sizep
'tk func.sysctlnametomib.args=3
'tk func.sysctlnametomib.ret=int
'tk func.system.arg.0=const char *,string
'tk func.system.args=1
'tk func.system.ret=int
'tk func.tan.arg.0=arithmetic,x
'tk func.tan.args=1
'tk func.tan.ret=floating_point
'tk func.tanf.arg.0=float,x
'tk func.tanf.args=1
'tk func.tanf.ret=float
'tk func.tanh.arg.0=arithmetic,x
'tk func.tanh.args=1
'tk func.tanh.ret=floating_point
'tk func.tanhf.arg.0=float,x
'tk func.tanhf.args=1
'tk func.tanhf.ret=float
'tk func.tanhl.arg.0=long double,x
'tk func.tanhl.args=1
'tk func.tanhl.ret=long double
'tk func.tanl.arg.0=long double,x
'tk func.tanl.args=1
'tk func.tanl.ret=long double
'tk func.tcgetpgrp.arg.0=int,fd
'tk func.tcgetpgrp.args=1
'tk func.tcgetpgrp.ret=pid_t
'tk func.textdomain.arg.0=char *,domainname
'tk func.textdomain.args=1
'tk func.textdomain.ret=char *
'tk func.tgamma.arg.0=arithmetic,x
'tk func.tgamma.args=1
'tk func.tgamma.ret=floating_point
'tk func.tgammaf.arg.0=float,x
'tk func.tgammaf.args=1
'tk func.tgammaf.ret=float
'tk func.tgammal.arg.0=long double,x
'tk func.tgammal.args=1
'tk func.tgammal.ret=long double
'tk func.tgetent.arg.0=const char *,bp
'tk func.tgetent.arg.1=const char *,name
'tk func.tgetent.args=2
'tk func.tgetent.ret=int
'tk func.tgetflag.arg.0=const char *,id
'tk func.tgetflag.args=1
'tk func.tgetflag.ret=int
'tk func.tgetnum.arg.0=char *,id
'tk func.tgetnum.args=1
'tk func.tgetnum.ret=int
'tk func.tgetstr.arg.0=char *,id
'tk func.tgetstr.arg.1=char **,area
'tk func.tgetstr.args=2
'tk func.tgetstr.ret=char*
'tk func.tgoto.arg.0=const char *,cap
'tk func.tgoto.arg.1=int,col
'tk func.tgoto.arg.2=int,row
'tk func.tgoto.args=3
'tk func.tgoto.ret=char *
'tk func.time.arg.0=time_t *,timer
'tk func.time.args=1
'tk func.time.ret=time_t
'tk func.tmpfile.args=0
'tk func.tmpfile.ret=file*
'tk func.tmpnam.arg.0=char *,s
'tk func.tmpnam.args=1
'tk func.tmpnam.ret=char *
'tk func.tolower.arg.0=int,c
'tk func.tolower.args=1
'tk func.tolower.ret=int
'tk func.toupper.arg.0=int,c
'tk func.toupper.args=1
'tk func.toupper.ret=int
'tk func.towctrans.arg.0=wint_t,wc
'tk func.towctrans.arg.1=wctrans_t,desc
'tk func.towctrans.args=2
'tk func.towctrans.ret=wint_t
'tk func.towlower.arg.0=wint_t,wc
'tk func.towlower.args=1
'tk func.towlower.ret=wint_t
'tk func.towupper.arg.0=wint_t,wc
'tk func.towupper.args=1
'tk func.towupper.ret=wint_t
'tk func.tputs.arg.0=const char *,str
'tk func.tputs.arg.1=int,affcnt
'tk func.tputs.arg.2=void *,putc
'tk func.tputs.args=3
'tk func.tputs.ret=int
'tk func.trunc.arg.0=arithmetic,x
'tk func.trunc.args=1
'tk func.trunc.ret=floating_point
'tk func.truncf.arg.0=float,x
'tk func.truncf.args=1
'tk func.truncf.ret=float
'tk func.truncl.arg.0=long double,x
'tk func.truncl.args=1
'tk func.truncl.ret=long double
'tk func.uClibc_main.arg.0=func,main
'tk func.uClibc_main.arg.1=int,argc
'tk func.uClibc_main.arg.2=char **,argv
'tk func.uClibc_main.arg.3=func,app_init
'tk func.uClibc_main.arg.4=func,app_fini
'tk func.uClibc_main.arg.5=func,rtld_fini
'tk func.uClibc_main.arg.6=void *,stack_end
'tk func.uClibc_main.args=7
'tk func.uClibc_main.noreturn=true
'tk func.uClibc_main.ret=int
'tk func.umask.arg.0=int,m
'tk func.umask.args=1
'tk func.umask.ret=int
'tk func.ungetc.arg.0=int,c
'tk func.ungetc.arg.1=FILE *,stream
'tk func.ungetc.args=2
'tk func.ungetc.ret=int
'tk func.ungetwc.arg.0=wint_t,c
'tk func.ungetwc.arg.1=FILE *,stream
'tk func.ungetwc.args=2
'tk func.ungetwc.ret=wint_t
'tk func.unlink.arg.0=const char *,path
'tk func.unlink.args=1
'tk func.unlink.ret=int
'tk func.user_from_uid.arg.0=uid_t,uid
'tk func.user_from_uid.arg.1=int,nouser
'tk func.user_from_uid.args=2
'tk func.user_from_uid.include=pwd.h
'tk func.user_from_uid.ret=char *
'tk func.usleep.arg.0=int,s
'tk func.usleep.args=1
'tk func.usleep.ret=int
'tk func.vfprintf.arg.0=FILE *,stream
'tk func.vfprintf.arg.1=const char *,format
'tk func.vfprintf.arg.2=va_list,ap
'tk func.vfprintf.args=3
'tk func.vfprintf.ret=int
'tk func.vfscanf.arg.0=FILE *,stream
'tk func.vfscanf.arg.1=const char *,format
'tk func.vfscanf.arg.2=va_list,ap
'tk func.vfscanf.args=3
'tk func.vfscanf.ret=int
'tk func.vfwprintf.arg.0=FILE *,stream
'tk func.vfwprintf.arg.1=const wchar_t *,format
'tk func.vfwprintf.arg.2=va_list,arg
'tk func.vfwprintf.args=3
'tk func.vfwprintf.ret=int
'tk func.vfwscanf.arg.0=FILE *,stream
'tk func.vfwscanf.arg.1=const wchar_t *,format
'tk func.vfwscanf.arg.2=va_list,arg
'tk func.vfwscanf.args=3
'tk func.vfwscanf.ret=int
'tk func.vprintf.arg.0=const char *,format
'tk func.vprintf.arg.1=va_list,ap
'tk func.vprintf.args=2
'tk func.vprintf.ret=int
'tk func.vscanf.arg.0=const char *,format
'tk func.vscanf.arg.1=va_list,ap
'tk func.vscanf.args=2
'tk func.vscanf.ret=int
'tk func.vsnprintf.arg.0=char *,s
'tk func.vsnprintf.arg.1=size_t,size
'tk func.vsnprintf.arg.2=const char *,format
'tk func.vsnprintf.arg.3=va_list,arg
'tk func.vsnprintf.args=4
'tk func.vsnprintf.ret=int
'tk func.vsprintf.arg.0=char *,s
'tk func.vsprintf.arg.1=const char *,format
'tk func.vsprintf.arg.2=va_list,arg
'tk func.vsprintf.args=3
'tk func.vsprintf.ret=int
'tk func.vsscanf.arg.0=const char *,s
'tk func.vsscanf.arg.1=const char *,format
'tk func.vsscanf.arg.2=va_list,arg
'tk func.vsscanf.args=3
'tk func.vsscanf.ret=int
'tk func.vswprintf.arg.0=wchar_t *,s
'tk func.vswprintf.arg.1=size_t,n
'tk func.vswprintf.arg.2=const wchar_t *,format
'tk func.vswprintf.arg.3=va_list,arg
'tk func.vswprintf.args=4
'tk func.vswprintf.ret=int
'tk func.vswscanf.arg.0=const wchar_t *,s
'tk func.vswscanf.arg.1=const wchar_t *,format
'tk func.vswscanf.arg.2=va_list,arg
'tk func.vswscanf.args=3
'tk func.vswscanf.ret=int
'tk func.vwprintf.arg.0=const wchar_t *,format
'tk func.vwprintf.arg.1=va_list,arg
'tk func.vwprintf.args=2
'tk func.vwprintf.ret=int
'tk func.vwscanf.arg.0=const wchar_t *,format
'tk func.vwscanf.arg.1=va_list,arg
'tk func.vwscanf.args=2
'tk func.vwscanf.ret=int
'tk func.wait.arg.0=int *,wstatus
'tk func.wait.args=1
'tk func.wait.ret=pid_t
'tk func.waitid.arg.0=idtype_t,idtype
'tk func.waitid.arg.1=id_t,id
'tk func.waitid.arg.2=siginfo_t *,infop
'tk func.waitid.arg.3=int,options
'tk func.waitid.args=4
'tk func.waitid.ret=int
'tk func.waitpid.arg.0=pid_t,pid
'tk func.waitpid.arg.1=int *,wstatus
'tk func.waitpid.arg.2=int,options
'tk func.waitpid.args=3
'tk func.waitpid.ret=pid_t
'tk func.warn.arg.0=int,eval
'tk func.warn.arg.1=const char *,fmt
'tk func.warn.args=2
'tk func.warn.ret=void
'tk func.warnc.arg.0=int,eval
'tk func.warnc.arg.1=int,code
'tk func.warnc.arg.2=const char *,fmt
'tk func.warnc.args=3
'tk func.warnc.ret=void
'tk func.warnx.arg.0=int,eval
'tk func.warnx.arg.1=const char *,fmt
'tk func.warnx.args=2
'tk func.warnx.ret=void
'tk func.wcrtomb.arg.0=char *,s
'tk func.wcrtomb.arg.1=wchar_t,wc
'tk func.wcrtomb.arg.2=mbstate_t *,ps
'tk func.wcrtomb.args=3
'tk func.wcrtomb.ret=size_t
'tk func.wcscat.arg.0=wchar_t *,s1
'tk func.wcscat.arg.1=const wchar_t *,s2
'tk func.wcscat.args=2
'tk func.wcscat.ret=wchar_t*
'tk func.wcschr.arg.0=wchar_t *,s
'tk func.wcschr.arg.1=wchar_t,c
'tk func.wcschr.args=2
'tk func.wcschr.ret=wchar_t*
'tk func.wcscmp.arg.0=const wchar_t *,s1
'tk func.wcscmp.arg.1=const wchar_t *,s2
'tk func.wcscmp.args=2
'tk func.wcscmp.ret=int
'tk func.wcscoll.arg.0=const wchar_t *,s1
'tk func.wcscoll.arg.1=const wchar_t *,s2
'tk func.wcscoll.args=2
'tk func.wcscoll.ret=int
'tk func.wcscpy.arg.0=wchar_t *,s1
'tk func.wcscpy.arg.1=const wchar_t *,s2
'tk func.wcscpy.args=2
'tk func.wcscpy.ret=wchar_t*
'tk func.wcscspn.arg.0=const wchar_t *,s1
'tk func.wcscspn.arg.1=const wchar_t *,s2
'tk func.wcscspn.args=2
'tk func.wcscspn.ret=size_t
'tk func.wcsftime.arg.0=wchar_t *,s
'tk func.wcsftime.arg.1=size_t,maxsize
'tk func.wcsftime.arg.2=const wchar_t *,format
'tk func.wcsftime.arg.3=const tm *,timeptr
'tk func.wcsftime.args=4
'tk func.wcsftime.ret=size_t
'tk func.wcslen.arg.0=const wchar_t *,s
'tk func.wcslen.args=1
'tk func.wcslen.ret=size_t
'tk func.wcsncat.arg.0=wchar_t *,s1
'tk func.wcsncat.arg.1=const wchar_t *,s2
'tk func.wcsncat.arg.2=size_t,n
'tk func.wcsncat.args=3
'tk func.wcsncat.ret=wchar_t*
'tk func.wcsncmp.arg.0=const wchar_t *,s1
'tk func.wcsncmp.arg.1=const wchar_t *,s2
'tk func.wcsncmp.arg.2=size_t,n
'tk func.wcsncmp.args=3
'tk func.wcsncmp.ret=int
'tk func.wcsncpy.arg.0=wchar_t *,s1
'tk func.wcsncpy.arg.1=const wchar_t *,s2
'tk func.wcsncpy.arg.2=size_t,n
'tk func.wcsncpy.args=3
'tk func.wcsncpy.ret=wchar_t*
'tk func.wcspbrk.arg.0=wchar_t *,s1
'tk func.wcspbrk.arg.1=const wchar_t *,s2
'tk func.wcspbrk.args=2
'tk func.wcspbrk.ret=wchar_t*
'tk func.wcsrchr.arg.0=wchar_t *,s
'tk func.wcsrchr.arg.1=wchar_t,c
'tk func.wcsrchr.args=2
'tk func.wcsrchr.ret=wchar_t*
'tk func.wcsrtombs.arg.0=char *,dst
'tk func.wcsrtombs.arg.1=const wchar_t* *,src
'tk func.wcsrtombs.arg.2=size_t,len
'tk func.wcsrtombs.arg.3=mbstate_t *,ps
'tk func.wcsrtombs.args=4
'tk func.wcsrtombs.ret=size_t
'tk func.wcsspn.arg.0=const wchar_t *,s1
'tk func.wcsspn.arg.1=const wchar_t *,s2
'tk func.wcsspn.args=2
'tk func.wcsspn.ret=size_t
'tk func.wcsstr.arg.0=wchar_t *,s1
'tk func.wcsstr.arg.1=const wchar_t *,s2
'tk func.wcsstr.args=2
'tk func.wcsstr.ret=wchar_t*
'tk func.wcstod.arg.0=const wchar_t *,nptr
'tk func.wcstod.arg.1=wchar_t* *,endptr
'tk func.wcstod.args=2
'tk func.wcstod.ret=double
'tk func.wcstof.arg.0=const wchar_t *,nptr
'tk func.wcstof.arg.1=wchar_t* *,endptr
'tk func.wcstof.args=2
'tk func.wcstof.ret=float
'tk func.wcstoimax.arg.0=const,wchar_t*
'tk func.wcstoimax.arg.1=wchar_t* *,endptr
'tk func.wcstoimax.arg.2=int,base
'tk func.wcstoimax.args=3
'tk func.wcstoimax.ret=intmax_t
'tk func.wcstok.arg.0=wchar_t *,s1
'tk func.wcstok.arg.1=const wchar_t *,s2
'tk func.wcstok.arg.2=wchar_t* *,ptr
'tk func.wcstok.args=3
'tk func.wcstok.ret=wchar_t*
'tk func.wcstol.arg.0=const wchar_t *,nptr
'tk func.wcstol.arg.1=wchar_t* *,endptr
'tk func.wcstol.arg.2=int,base
'tk func.wcstol.args=3
'tk func.wcstol.ret=long
'tk func.wcstold.arg.0=const wchar_t *,nptr
'tk func.wcstold.arg.1=wchar_t* *,endptr
'tk func.wcstold.args=2
'tk func.wcstold.ret=long double
'tk func.wcstoll.arg.0=const wchar_t *,nptr
'tk func.wcstoll.arg.1=wchar_t* *,endptr
'tk func.wcstoll.arg.2=int,base
'tk func.wcstoll.args=3
'tk func.wcstoll.ret=long long
'tk func.wcstombs.arg.0=char *,s
'tk func.wcstombs.arg.1=const wchar_t *,pwcs
'tk func.wcstombs.arg.2=size_t,n
'tk func.wcstombs.args=3
'tk func.wcstombs.ret=size_t
'tk func.wcstoul.arg.0=const wchar_t *,nptr
'tk func.wcstoul.arg.1=wchar_t* *,endptr
'tk func.wcstoul.arg.2=int,base
'tk func.wcstoul.args=3
'tk func.wcstoul.ret=long
'tk func.wcstoull.arg.0=const wchar_t *,nptr
'tk func.wcstoull.arg.1=wchar_t* *,endptr
'tk func.wcstoull.arg.2=int,base
'tk func.wcstoull.args=3
'tk func.wcstoull.ret=long long
'tk func.wcstoumax.arg.0=const,wchar_t*
'tk func.wcstoumax.arg.1=wchar_t* *,endptr
'tk func.wcstoumax.arg.2=int,base
'tk func.wcstoumax.args=3
'tk func.wcstoumax.ret=uintmax_t
'tk func.wcsxfrm.arg.0=wchar_t *,s1
'tk func.wcsxfrm.arg.1=const wchar_t *,s2
'tk func.wcsxfrm.arg.2=size_t,n
'tk func.wcsxfrm.args=3
'tk func.wcsxfrm.ret=size_t
'tk func.wctob.arg.0=wint_t,c
'tk func.wctob.args=1
'tk func.wctob.ret=int
'tk func.wctomb.arg.0=char *,s
'tk func.wctomb.arg.1=wchar_t,wchar
'tk func.wctomb.args=2
'tk func.wctomb.ret=int
'tk func.wctrans.arg.0=const char *,property
'tk func.wctrans.args=1
'tk func.wctrans.ret=wctrans_t
'tk func.wctype.arg.0=const char *,property
'tk func.wctype.args=1
'tk func.wctype.ret=wctype_t
'tk func.wmemchr.arg.0=wchar_t *,s
'tk func.wmemchr.arg.1=wchar_t,c
'tk func.wmemchr.arg.2=size_t,n
'tk func.wmemchr.args=3
'tk func.wmemchr.ret=wchar_t*
'tk func.wmemcmp.arg.0=wchar_t *,s1
'tk func.wmemcmp.arg.1=const wchar_t *,s2
'tk func.wmemcmp.arg.2=size_t,n
'tk func.wmemcmp.args=3
'tk func.wmemcmp.ret=int
'tk func.wmemcpy.arg.0=wchar_t *,s1
'tk func.wmemcpy.arg.1=const wchar_t *,s2
'tk func.wmemcpy.arg.2=size_t,n
'tk func.wmemcpy.args=3
'tk func.wmemcpy.ret=wchar_t*
'tk func.wmemmove.arg.0=wchar_t *,s1
'tk func.wmemmove.arg.1=const wchar_t *,s2
'tk func.wmemmove.arg.2=size_t,n
'tk func.wmemmove.args=3
'tk func.wmemmove.ret=wchar_t*
'tk func.wmemset.arg.0=wchar_t *,s
'tk func.wmemset.arg.1=wchar_t,c
'tk func.wmemset.arg.2=size_t,n
'tk func.wmemset.args=3
'tk func.wmemset.ret=wchar_t*
'tk func.wprintf.arg.0=const wchar_t *,format
'tk func.wprintf.args=1
'tk func.wprintf.ret=int
'tk func.write.arg.0=int,fd
'tk func.write.arg.1=const char *,ptr
'tk func.write.arg.2=size_t,nbytes
'tk func.write.args=3
'tk func.write.ret=ssize_t
'tk func.wscanf.arg.0=const wchar_t *,format
'tk func.wscanf.arg.1=,...
'tk func.wscanf.args=2
'tk func.wscanf.ret=int
'tk func.xalloc_die.args=0
'tk func.xalloc_die.noreturn=true
'tk func.xalloc_die.ret=void
'tk func.xmalloc.arg.0=size_t,size
'tk func.xmalloc.args=1
'tk func.xmalloc.ret= void *
'tk fwide=func
'tk fwprintf=func
'tk fwrite=func
'tk fwscanf=func
'tk getbsize=func
'tk getc=func
'tk getchar=func
'tk getenv=func
'tk geteuid=func
'tk getopt=func
'tk getopt_long=func
'tk getpid=func
'tk getprogname=func
'tk gets=func
'tk getsockname=func
'tk getsockopt=func
'tk getuid=func
'tk getwc=func
'tk getwchar=func
'tk gid_t=type
'tk gmtime=func
'tk group_from_gid=func
'tk humanize_number=func
'tk hypot=func
'tk hypotf=func
'tk hypotl=func
'tk ilogb=func
'tk ilogbf=func
'tk ilogbl=func
'tk imaxabs=func
'tk imaxdiv=func
'tk inet_aton=func
'tk inet_ntoa=func
'tk initstate=func
'tk int=type
'tk int16_t=type
'tk int32_t=type
'tk int64_t=type
'tk int8_t=type
'tk ioctl=func
'tk isalnum=func
'tk isalpha=func
'tk isatty=func
'tk isblank=func
'tk iscntrl=func
'tk isdigit=func
'tk isfinite=func
'tk isgraph=func
'tk isgreater=func
'tk isgreaterequal=func
'tk isinf=func
'tk isless=func
'tk islessequal=func
'tk islessgreater=func
'tk islower=func
'tk isnan=func
'tk isnormal=func
'tk isprint=func
'tk ispunct=func
'tk isspace=func
'tk isunordered=func
'tk isupper=func
'tk iswalnum=func
'tk iswalpha=func
'tk iswblank=func
'tk iswcntrl=func
'tk iswctype=func
'tk iswdigit=func
'tk iswgraph=func
'tk iswlower=func
'tk iswprint=func
'tk iswpunct=func
'tk iswspace=func
'tk iswupper=func
'tk iswxdigit=func
'tk isxdigit=func
'tk kill=func
'tk labs=func
'tk ldexp=func
'tk ldexpf=func
'tk ldexpl=func
'tk ldiv=func
'tk lgamma=func
'tk lgammaf=func
'tk lgammal=func
'tk libc_init=func
'tk libc_init_array=func
'tk libc_start_main=func
'tk listxattr=func
'tk llabs=func
'tk lldiv=func
'tk llrint=func
'tk llrintf=func
'tk llrintl=func
'tk llround=func
'tk llroundf=func
'tk llroundl=func
'tk localeconv=func
'tk localtime=func
'tk log=func
'tk log10=func
'tk log10f=func
'tk log10l=func
'tk log1p=func
'tk log1pf=func
'tk log1pl=func
'tk log2=func
'tk log2f=func
'tk log2l=func
'tk logb=func
'tk logbf=func
'tk logbl=func
'tk logf=func
'tk logl=func
'tk long=type
'tk long long=type
'tk longjmp=func
'tk lrint=func
'tk lrintf=func
'tk lrintl=func
'tk lround=func
'tk lroundf=func
'tk lroundl=func
'tk lstat=func
'tk main=func
'tk malloc=func
'tk maskrune=func
'tk mblen=func
'tk mbrlen=func
'tk mbrtowc=func
'tk mbsinit=func
'tk mbsrtowcs=func
'tk mbstowcs=func
'tk mbtowc=func
'tk memchr=func
'tk memcmp=func
'tk memcpy=func
'tk memmem=func
'tk memmove=func
'tk memset=func
'tk mkstemp=func
'tk mktemp=func
'tk mktime=func
'tk mmap=func
'tk modf=func
'tk modff=func
'tk modfl=func
'tk munmap=func
'tk nan=func
'tk nanf=func
'tk nanl=func
'tk nanosleep=func
'tk nearbyint=func
'tk nearbyintf=func
'tk nearbyintl=func
'tk nextafter=func
'tk nextafterf=func
'tk nextafterl=func
'tk nexttoward=func
'tk nexttowardf=func
'tk nexttowardl=func
'tk nl_langinfo=func
'tk nl_langinfo_l=func
'tk objc_allocWithZone=func
'tk objc_enumerationMutation=func
'tk objc_msgSend=func
'tk objc_msgSendSuper2=func
'tk objc_opt_self=func
'tk objc_release=func
'tk objc_retain=func
'tk objc_retainAutoreleasedReturnValue=func
'tk objc_storeStrong=func
'tk open=func
'tk openat=func
'tk pclose=func
'tk perror=func
'tk pid_t=type
'tk popen=func
'tk pow=func
'tk powf=func
'tk powl=func
'tk prctl=func
'tk printf=func
'tk ptrace=func
'tk putc=func
'tk putchar=func
'tk puts=func
'tk pututxline=func
'tk putwc=func
'tk putwchar=func
'tk qsort=func
'tk quick_exit=func
'tk raise=func
'tk rand=func
'tk random=func
'tk read=func
'tk readlink=func
'tk realloc=func
'tk reallocf=func
'tk recv=func
'tk recvfrom=func
'tk remainder=func
'tk remainderf=func
'tk remainderl=func
'tk remove=func
'tk remquo=func
'tk remquof=func
'tk remquol=func
'tk rename=func
'tk rewind=func
'tk rint=func
'tk rintf=func
'tk rintl=func
'tk round=func
'tk roundf=func
'tk roundl=func
'tk scalbln=func
'tk scalblnf=func
'tk scalblnl=func
'tk scalbn=func
'tk scalbnf=func
'tk scalbnl=func
'tk scanf=func
'tk select=func
'tk send=func
'tk setbuf=func
'tk setenv=func
'tk setgid=func
'tk setjmp=func
'tk setlocale=func
'tk setsockopt=func
'tk setstate=func
'tk setuid=func
'tk setvbuf=func
'tk short=type
'tk sigaction=func
'tk signal=func
'tk signbit=func
'tk sigprocmask=func
'tk sin=func
'tk sinf=func
'tk sinh=func
'tk sinhf=func
'tk sinhl=func
'tk sinl=func
'tk size_t=type
'tk sleep=func
'tk snprintf=func
'tk snprintf_chk=func
'tk socket=func
'tk sprintf=func
'tk sprintf_chk=func
'tk sqrt=func
'tk sqrtf=func
'tk sqrtl=func
'tk srand=func
'tk srandom=func
'tk srandomdev=func
'tk sscanf=func
'tk stack_chk_fail=func
'tk strcasecmp=func
'tk strcat=func
'tk strchr=func
'tk strcmp=func
'tk strcoll=func
'tk strcpy=func
'tk strcpy_chk=func
'tk strcspn=func
'tk strdup=func
'tk strerror=func
'tk strftime=func
'tk strlcpy=func
'tk strlen=func
'tk strmode=func
'tk strncasecmp=func
'tk strncat=func
'tk strncmp=func
'tk strncpy=func
'tk strndup=func
'tk strpbrk=func
'tk strrchr=func
'tk strspn=func
'tk strstr=func
'tk strtod=func
'tk strtof=func
'tk strtoimax=func
'tk strtok=func
'tk strtol=func
'tk strtold=func
'tk strtoll=func
'tk strtonum=func
'tk strtoul=func
'tk strtoull=func
'tk strtoumax=func
'tk struct.NSString=p0,p1,str,len
'tk struct.NSString.len=int,0,0
'tk struct.NSString.len.meta=4
'tk struct.NSString.p0=void *,0,0
'tk struct.NSString.p0.meta=4
'tk struct.NSString.p1=size_t,0,0
'tk struct.NSString.p1.meta=4
'tk struct.NSString.str=char *,0,0
'tk struct.NSString.str.meta=4
'tk strxfrm=func
'tk swift_beginAccess=func
'tk swift_bridgeObjectRelease=func
'tk swift_bridgeObjectRetain=func
'tk swift_endAccess=func
'tk swift_getObjCClassFromMetadata=func
'tk swift_initStackObject=func
'tk swift_release=func
'tk swift_unexpectedError=func
'tk swprintf=func
'tk swscanf=func
'tk symlink=func
'tk sysctl=func
'tk sysctlbyname=func
'tk sysctlnametomib=func
'tk system=func
'tk tan=func
'tk tanf=func
'tk tanh=func
'tk tanhf=func
'tk tanhl=func
'tk tanl=func
'tk tcgetpgrp=func
'tk textdomain=func
'tk tgamma=func
'tk tgammaf=func
'tk tgammal=func
'tk tgetent=func
'tk tgetflag=func
'tk tgetnum=func
'tk tgetstr=func
'tk tgoto=func
'tk time=func
'tk tmpfile=func
'tk tmpnam=func
'tk tolower=func
'tk toupper=func
'tk towctrans=func
'tk towlower=func
'tk towupper=func
'tk tputs=func
'tk trunc=func
'tk truncf=func
'tk truncl=func
'tk type.FILE=p
'tk type.FILE.size=8
'tk type.char=c
'tk type.char *=z
'tk type.char **=*z
'tk type.char *.size=32
'tk type.char.size=8
'tk type.double=F
'tk type.double.size=64
'tk type.float=f
'tk type.float.size=32
'tk type.func=p
'tk type.func.size=8
'tk type.gid_t=d
'tk type.gid_t.uid=32
'tk type.int=d
'tk type.int.size=32
'tk type.int16_t=w
'tk type.int16_t.size=16
'tk type.int32_t=d
'tk type.int32_t.size=32
'tk type.int64_t=q
'tk type.int64_t.size=64
'tk type.int8_t=b
'tk type.int8_t.size=8
'tk type.long=x
'tk type.long long=q
'tk type.long long.size=64
'tk type.long.size=64
'tk type.pid_t=d
'tk type.pid_t.pid=32
'tk type.pid_t.size=32
'tk type.short=w
'tk type.short.size=16
'tk type.size_t=d
'tk type.size_t.size=32
'tk type.uid_t=d
'tk type.uid_t.size=64
'tk type.uid_t.uid=32
'tk type.uint16_t=w
'tk type.uint16_t.size=16
'tk type.uint32_t=d
'tk type.uint32_t.size=32
'tk type.uint64_t=q
'tk type.uint64_t.size=64
'tk type.uint8_t=b
'tk type.uint8_t.size=8
'tk type.unsigned char=b
'tk type.unsigned char.size=8
'tk type.unsigned int=i
'tk type.unsigned int.size=32
'tk type.unsigned short=w
'tk type.unsigned short.size=16
'tk type.void *=p
'tk type.void *.size=32
'tk uClibc_main=func
'tk uid_t=type
'tk uint16_t=type
'tk uint32_t=type
'tk uint64_t=type
'tk uint8_t=type
'tk umask=func
'tk ungetc=func
'tk ungetwc=func
'tk unlink=func
'tk unsigned char=type
'tk unsigned int=type
'tk unsigned short=type
'tk user_from_uid=func
'tk usleep=func
'tk vfprintf=func
'tk vfscanf=func
'tk vfwprintf=func
'tk vfwscanf=func
'tk void *=type
'tk vprintf=func
'tk vscanf=func
'tk vsnprintf=func
'tk vsprintf=func
'tk vsscanf=func
'tk vswprintf=func
'tk vswscanf=func
'tk vwprintf=func
'tk vwscanf=func
'tk wait=func
'tk waitid=func
'tk waitpid=func
'tk warn=func
'tk warnc=func
'tk warnx=func
'tk wcrtomb=func
'tk wcscat=func
'tk wcschr=func
'tk wcscmp=func
'tk wcscoll=func
'tk wcscpy=func
'tk wcscspn=func
'tk wcsftime=func
'tk wcslen=func
'tk wcsncat=func
'tk wcsncmp=func
'tk wcsncpy=func
'tk wcspbrk=func
'tk wcsrchr=func
'tk wcsrtombs=func
'tk wcsspn=func
'tk wcsstr=func
'tk wcstod=func
'tk wcstof=func
'tk wcstoimax=func
'tk wcstok=func
'tk wcstol=func
'tk wcstold=func
'tk wcstoll=func
'tk wcstombs=func
'tk wcstoul=func
'tk wcstoull=func
'tk wcstoumax=func
'tk wcsxfrm=func
'tk wctob=func
'tk wctomb=func
'tk wctrans=func
'tk wctype=func
'tk wmemchr=func
'tk wmemcmp=func
'tk wmemcpy=func
'tk wmemmove=func
'tk wmemset=func
'tk wprintf=func
'tk write=func
'tk wscanf=func
'tk xalloc_die=func
'tk xmalloc=func
# macros

# aliases
# seek
s 0x00000000
