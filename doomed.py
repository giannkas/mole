#!/usr/bin/env python

import multiprocessing
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time

from tqdm import tqdm

import networkx as nx

import clingo

DEVNULL = open(os.devnull, 'wb')

script_dir = os.path.dirname(__file__)
def script_path(name):
    return os.path.join(script_dir, name)

class Model:
  def __init__(self, filename):
    if os.path.isfile(filename + ".ll_net"):
      self.filename = filename + ".ll_net"
    else:
      self.filename = filename + ".ll"
    self.suffix = self.filename.split('.')[-1]
    self.read(open(self.filename))

  def read(self, f):
    self.header = ''
    self.PL = {}
    self.TR = []
    self.RT = []
    self.RD = []
    self.TP = []
    self.PT = []
    self.RS = []
    self.PL_ = {}
    self.TR_ = []
    self.RT_ = []
    self.RD_ = []
    self.TP_ = []
    self.PT_ = []
    self.RS_ = []
    state = "header"
    max_pid = 0
    max_tid = 0
    pid, tid = 0, 0
    for l in f:
      r = l.strip()
      if r in ["PL", "TR", "RT", "RD", "TP", "PT", "RS"]:
        state = r
      elif state == "header":
        self.header += l
      elif state == "PL":
        parts = r.split('"')
        if len(parts[0]) < 1: pid += 1
        else: pid = int(parts[0])
        name = parts[1]
        m0 = "M1" in r
        self.PL[name] = {"id": pid, "m0": m0}
        max_pid = max(max_pid, pid)
      elif state == "TR":
        parts = r.split('"')
        if len(parts[0]) < 1: tid += 1
        else: tid = int(parts[0])
        max_tid = max(max_tid, tid)
        self.TR.append(r)
      elif state == "RT":
        self.RT.append(r)
      elif state == "RD":
        self.RD.append(r)
      elif state == "TP":
        self.TP.append(r)
      elif state == "PT":
        self.PT.append(r)
      elif state == "RS":
        self.RS.append(r)
    self.max_pid = max_pid
    self.max_tid = max_tid

  def write(self, f):
    f.write(self.header)
    PL = ["%d\"%s\"M%d" % (v["id"], k, 1 if v["m0"] else 0)
            for k, v in self.PL.items()]
    f.write("PL\n%s\n" % ("\n".join(PL)))
    f.write("TR\n%s\n" % ("\n".join(self.TR + self.TR_)))
    f.write("RT\n%s\n" % ("\n".join(self.RT + self.RT_)))
    f.write("RD\n%s\n" % ("\n".join(self.RD + self.RD_)))
    f.write("TP\n%s\n" % ("\n".join(self.TP + self.TP_)))
    f.write("PT\n%s\n" % ("\n".join(self.PT + self.PT_)))
    f.write("RS\n%s\n" % ("\n".join(self.RS + self.RS_)))

  def set_marking(self, m0):
    for k in self.PL:
      self.PL[k]["m0"] = k in m0

  def complix(self, mcifile="working.mci", verbose=False):
    llfile = os.path.join(out_d, "working.ll")
    with open(llfile, "w") as fp:
        self.write(fp)
    mcifile = os.path.join(out_d, mcifile)
    subprocess.check_call(["ecofolder", "-data", llfile, "-m", mcifile],
        stderr=subprocess.DEVNULL if not verbose else None)
    return mcifile


def prefix_nb_events(mcifile):
  # includes cutoffs
  with open(mcifile, "rb") as fp:
      _, nbev = struct.unpack("ii", fp.read(8))
  return nbev


def py_of_symbol(symb):
  if symb.type is clingo.SymbolType.String:
      return symb.string
  if symb.type is clingo.SymbolType.Number:
      return symb.number
  if symb.type is clingo.SymbolType.Function:
      if symb.arguments:
          return tuple(map(py_of_symbol, symb.arguments))
      else:
          return symb.name
  raise ValueError


def h(m):
  return tuple(sorted(m))

def get_eid(x):
  return f"""({x[0].strip("'")},{x[1].strip("'")})"""

def marking_from_atoms(atoms):
  return h({py_of_symbol(a.arguments[0]) for a in atoms
      if a.name == "ncut"})
def cut_from_atoms(atoms):
  return h({py_of_symbol(a.arguments[0]) for a in atoms
        if a.name == "cut"})
def hcut_from_atoms(atoms):
  return h({py_of_symbol(a) for a in atoms
            if a.name == "hcut"})
def cfg_from_atoms(atoms):
  return h({get_eid(py_of_symbol(a.arguments[0])) for a in atoms
          if a.name == "e"})
def names_from_atoms(atoms):
  return {py_of_symbol(a.arguments[0]) for a in atoms
          if a.name == "resolved"}

def asp_of_mci(mcifile, ns=None):
  args = [script_path("mci2asp"), mcifile]
  if ns:
    args.append(str(ns))
  return subprocess.check_output(args).decode()

def asp_of_sig_cfg(i, cfg, sig):
  facts = [f"mcfg(cfg{i},{e})." for e in cfg]
  facts += [f"sig_mcfg(cfg{i},{s})." for s in sig]
  return " ".join(facts)

def dot_from_atoms(atoms):
  dot = "digraph G {\n"
  for a in atoms:
      if a.name == "draw":
          a, b = [py_of_symbol(x) for x in a.arguments]
          dot += f"  {a} -> {b};\n"
      elif a.name == "label":
          a, b = [py_of_symbol(x) for x in a.arguments]
          shape = "box" if a[0] == "e" else "none"
          b = "\""+b+"\""
          dot += f"  {a} [label={b} shape={shape}];\n"
  dot += "}\n"
  return dot


def prefix_has_marking(prefix_asp, markings):
  sat = clingo.Control([1]+clingo_opts)
  sat.add("base", [], prefix_asp)
  sat.load(script_path("configuration.asp"))
  sat.load(script_path("anycfg.asp"))
  sat.load(script_path("cut.asp"))
  for i, m in enumerate(markings):
      sat.add("base", [], "".join(["q({},\"{}\").".format(i,p) for p in m]))
  sat.add("base", [],
      "bad(I) :- q(I,_), ncut(P), not q(I,P)."
      "bad(I) :- not ncut(P), q(I,P)."
      "ok :- q(I,_), not bad(I)."
      ":- not ok.")
  sat.ground([("base",())])
  return sat.solve().satisfiable

def markings(prefix_asp):
  sat = clingo.Control([0, "--project"]+clingo_opts)
  sat.add("base", [], prefix_asp)
  sat.load(script_path("configuration.asp"))
  sat.load(script_path("anycfg.asp"))
  sat.load(script_path("cut.asp"))
  sat.add("base", [], "#show.")
  sat.add("base", [], "#show ncut/1.")
  sat.ground([("base",())])
  for sol in sat.solve(yield_=True):
    atoms = sol.symbols(shown=True)
    m = marking_from_atoms(atoms)
    yield m

def maximal_configurations(prefix_asp):
  sat = clingo.Control(["0", "--heuristic=Domain",
      "--enum-mode=domRec", "--dom-mod=3,16"]+clingo_opts)
  sat.add("base", [], prefix_asp)
  sat.load(script_path("configuration.asp"))
  sat.load(script_path("anycfg.asp"))
  sat.load(script_path("cut.asp"))
  sat.add("base", [], "#show e/1.")
  #sat.load(script_path("maxcfg.asp"))
  sat.ground([("base",())])
  for sol in sat.solve(yield_=True):
    atoms = sol.symbols(atoms=True)
    info = {
        "marking": marking_from_atoms(atoms),
        "cfg": cfg_from_atoms(atoms),
        "hcut": hcut_from_atoms(atoms),
    }
    yield info

def find_glue(hcut, prefix_asp):
  sat = clingo.Control(["1"]+clingo_opts)
  sat.add("base", [], prefix_asp)
  for (c,p) in hcut:
    sat.add("base", [], f"hcut({c},{p}).")
  sat.load(script_path("findglue.asp"))
  sat.ground([("base",())])
  for sol in sat.solve(yield_=True):
    atoms = sol.symbols(shown=True)
    def parse_bind(a):
        l, r = py_of_symbol(a)
        return (get_eid(l),get_eid(r))
    b = [parse_bind(a) for a in atoms if a.name == "bind"]
    yield b

def minF0(prefix_asp, bad_aspfile):
  sat = clingo.Control(["0", "--heuristic=Domain",
      "--enum-mode=domRec", "--dom-mod=3,16"]+clingo_opts)
  sat.add("base", [], prefix_asp)
  sat.load(bad_aspfile)
  sat.load(script_path("f0.asp"))
  sat.ground([("base",())])
  for sol in sat.solve(yield_=True):
    atoms = sol.symbols(atoms=True)
    cfg = cfg_from_atoms(atoms)
    yield cfg

def get_event_poset(prefix_asp):
  c = clingo.Control(["1"]+clingo_opts)
  c.add("base", [], prefix_asp)
  c.load(script_path("get_event_poset.asp"))
  c.ground([("base",())])
  sol = next(iter(c.solve(yield_=True)))
  atoms = sol.symbols(shown=True)
  edges = [(get_eid(py_of_symbol(a.arguments[0])), get_eid(py_of_symbol(a.arguments[1])))
              for a in atoms if a.name == "greater"]
  unchallenged = set((get_eid(py_of_symbol(a.arguments[0]))) for a in atoms if a.name == "unchallenged")
  poset = nx.DiGraph(edges)
  e2tr = {get_eid(py_of_symbol(a.arguments[0])): py_of_symbol(a.arguments[1])
              for a in atoms if a.name == "e2tr"}
  return {
      "poset": poset,
      "unchallenged": unchallenged,
      "e2tr": e2tr
  }

model_ll = sys.argv[1]
bad_marking = sys.argv[2]
model = Model(model_ll)

base_output = os.path.basename(model_ll.replace(".ll", ""))
out_d = f"gen/{base_output}"

if os.path.exists(out_d):
    shutil.rmtree(out_d)
os.makedirs(out_d)

bad_aspfile = os.path.join(out_d, "bad.asp")
with open(bad_aspfile, "w") as fp:
  for p in bad_marking.split(","):
    fp.write(f"{clingo.Function('bad', (clingo.String(p),))}.\n")

clingo_opts = ["-W", "none"]
#clingo_opts += ["-t", str(multiprocessing.cpu_count())]

t0 = time.time()

# compute main prefix
mci = model.complix("main.mci", verbose=1)
prefix = asp_of_mci(mci)
print(f"Prefix has {prefix_nb_events(mci)} events, including cut-offs",
        file=sys.stderr)
with open(f"{out_d}/prefix.asp", "w") as fp:
    fp.write(prefix)

prefix_info = get_event_poset(prefix)
prefix_d = prefix_info["poset"]
unchallenged = prefix_info["unchallenged"]
e2tr = prefix_info["e2tr"]

print("Unchallenged events", unchallenged, file=sys.stderr)

# compute Pi_1

maxcfg = list(tqdm(maximal_configurations(prefix),
            desc="(Pi_1) Computing maximal configurations without cut-offs"))
prefixes = []
for i, info in enumerate(tqdm(maxcfg, desc="(Pi_1) Computing prefixes")):
  model.set_marking(set(info["marking"]))
  #print(info)
  mci = model.complix()
  ns = f"w{i}"
  mci_asp = asp_of_mci(mci, ns=ns)
  for j, glue in enumerate(find_glue(info["hcut"], mci_asp)):
      if not glue:
          continue
      w_asp = mci_asp
      for (orig, match) in glue:
          w_asp = w_asp.replace(f"{match},",f"{orig},")
      prefixes.append(w_asp)
      """
      with open(f"{out_d}/p{i}{j}.asp", "w") as fp:
          fp.write(w_asp)
      """

Pi1_asp = "".join([prefix]+prefixes)
with open(f"{out_d}/pi1.asp", "w") as fp:
  fp.write(Pi1_asp)

def get_crest(poset):
  return {e for e, od in poset.out_degree() if od == 0}

stats = {
    "is_doomed": 0
}

def shave(C_d, crest):
  first = True
  blacklist = set()
  crest = set(crest)
  while True:
    rm = [e for e in crest if e in unchallenged]
    if not rm:
        break
    crest.difference_update(rm)
    blacklist.update(rm)
    for e in rm:
      for f in C_d.predecessors(e):
        is_crest = True
        for g in C_d.successors(f):
          if g not in blacklist:
              is_crest = False
              break
        if is_crest:
          crest.add(f)
  return tuple(sorted(set(C_d) - blacklist)), tuple(sorted(crest))

from time import process_time

wl = set()
known = set()
for C in tqdm(minF0(prefix, bad_aspfile), desc="minFO"):
  #print("C", C)
  C_d = prefix_d.subgraph(C)
  C_crest = get_crest(C_d)
  (keep, crest) = shave(C_d, C_crest)
  #print("C_shave", keep)
  wl.add((keep, crest))


print("Grounding doom check...", end="", flush=True, file=sys.stderr)
t0 = process_time()
doom_ctl = clingo.Control(clingo_opts)
doom_ctl.load(script_path("viable.asp"))
doom_ctl.load(bad_aspfile)
doom_ctl.load(f"{out_d}/pi1.asp")
doom_ctl.ground([("base",())])
print(f" done in {process_time()-t0:.1f}s", flush=True, file=sys.stderr)

def is_doomed(C):
  terms = [clingo.parse_term(f"my({e})") for e in C]
  for t in terms:
      doom_ctl.assign_external(t, True)
  ret = not doom_ctl.solve().satisfiable
  for t in terms:
      doom_ctl.release_external(t)
  stats["is_doomed"] += 1
  return ret

def handle(C_e):
  if is_doomed(C_e):
    C_d = prefix_d.subgraph(C_e)
    C_crest = get_crest(C_d)
    Cp = shave(C_d, C_crest)
    wl.add(Cp)
    return False
  return True

i = 0
while wl:
  C, crest = wl.pop()
  if C in known:
    continue
  known.add(C)
  C = set(C)
  crest = set(crest)
  #print("wl", C)
  #print("  crest =", crest)
  C_e = C - crest
  add = True
  if handle(C - crest):
    for e in crest:
      viable = handle(C - {e})
      add = add and viable
  else:
    add = False
  if add:
    i += 1
    d = process_time() - t0
    print(f"{d:.1f} [MINDOO {i}]\t", set(sorted([e2tr[e] for e in C])), list(sorted(C)), flush=True)
    print(f"   doom checks: {stats['is_doomed']}", flush=True, file=sys.stderr)
if i == 0:
  print("EMPTY MINDOO")
print(f"total doom checks: {stats['is_doomed']}", flush=True, file=sys.stderr)
