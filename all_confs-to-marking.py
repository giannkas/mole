#!/usr/bin/env python

import multiprocessing
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import time
import re

from tqdm import tqdm

import networkx as nx

import clingo

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
    self.posts_TR = {}
    self.RT = []
    self.RD = []
    self.TP = []
    self.PT = []
    self.RS = []
    state = "header"
    max_pid = 0
    max_tid = 0
    pid, tid = 0, 0
    id2pn = {}
    id2tn = {}
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
        m0 = r.endswith("M1")
        self.PL[name] = {"id": pid, "m0": m0}
        id2pn[pid] = name
        max_pid = max(max_pid, pid)
      elif state == "TR":
        parts = r.split('"')
        if len(parts[0]) < 1: tid += 1
        else: tid = int(parts[0])
        name = parts[1]
        id2tn[tid] = name
        max_tid = max(max_tid, tid)
        self.TR.append(r)
      elif state == "RT":
        self.RT.append(r)
      elif state == "RD":
        self.RD.append(r)
      elif state == "TP":
        self.TP.append(r)
        parts = r.split("<")
        parts[0] = int(parts[0])
        parts[1] = int(parts[1])
        if id2tn[parts[0]] not in self.posts_TR: 
          self.posts_TR[id2tn[parts[0]]] = [id2pn[parts[1]]]
        else: self.posts_TR[id2tn[parts[0]]] += [id2pn[parts[1]]]
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
    f.write("TR\n%s\n" % ("\n".join(self.TR)))
    f.write("RT\n%s\n" % ("\n".join(self.RT)))
    f.write("RD\n%s\n" % ("\n".join(self.RD)))
    f.write("TP\n%s\n" % ("\n".join(self.TP)))
    f.write("PT\n%s\n" % ("\n".join(self.PT)))
    f.write("RS\n%s\n" % ("\n".join(self.RS)))

  def set_marking(self, m0):
    for k in self.PL:
      self.PL[k]["m0"] = k in m0
  
  def get_m0(self):
    m0 = []
    for i in self.PL:
      if self.PL[i]["m0"] is True:
        m0+=[i]
    return m0

  def complix(self, mcifile="working.mci", verbose=False):
    llfile = os.path.join(out_d, "working.ll")
    with open(llfile, "w") as fp:
        self.write(fp)
    mcifile = os.path.join(out_d, mcifile)
    subprocess.check_call(["ecofolder", "-useids", llfile, "-m", mcifile],
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
  args = [script_path("mci2asp"), mcifile, "-p"]
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

def minF0(prefix_asp, bad_aspfile):
  sat = clingo.Control(["0", "--heuristic=Domain",
      "--enum-mode=domRec", "--dom-mod=3,16"]+clingo_opts)
  sat.add("base", [], prefix_asp)
  sat.load(bad_aspfile)
  #sat.load(script_path("configuration.asp"))
  #sat.load(script_path("anycfg.asp"))
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
f = open(bad_marking)
bad_markings = []
for l in f: # reading bad markings in f
  bad_markings += [l.strip().split(",")] # list of lists to store each bad marking
with open(bad_aspfile, "w") as fp:
  for m in bad_markings:
    for p in m:
      fp.write(f"{clingo.Function('bad', (clingo.String(p),))}.\n")

clingo_opts = ["-W", "none"]
#clingo_opts += ["-t", str(multiprocessing.cpu_count())]

t0 = time.time()

# compute main prefix
mci = model.complix("main.mci", verbose=1)
prefix = asp_of_mci(mci)
#dicevents = evstump_of_mci(mci)
#print(dicevents)
print(f"Prefix has {prefix_nb_events(mci)} events, including cut-offs",
        file=sys.stderr)

with open(f"{out_d}/prefix.asp", "w") as fp:
  fp.write(prefix)

prefix_info = get_event_poset(prefix)
prefix_d = prefix_info["poset"]
unchallenged = prefix_info["unchallenged"]
e2tr = prefix_info["e2tr"]

print("Unchallenged events", unchallenged, file=sys.stderr)
print("prefix_d", prefix_d)

def get_crest(poset):
  return {e for e, od in poset.out_degree() if od == 0}

stats = {
  "freechk": 0
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

from time import strftime

wl = set()
known = set()
init_marking = model.get_m0()
empty_wl = 1
for i in bad_markings:
  if len(i) < len(init_marking):
    for j in i:
      if j not in init_marking: empty_wl = 0
  elif len(i) > len(init_marking): empty_wl = 0
  elif len(i) == len(init_marking):
    if set(i) != set(init_marking):
      empty_wl = 0

if not empty_wl:
  for C in tqdm(minF0(prefix, bad_aspfile), desc="minFO"):
    wl.add((C))

#t0 = process_time()
doom_ctl = clingo.Control(clingo_opts)

def str_conf(C):
  Cstr = ""
  for s in C:
    Cstr = Cstr + "".join(s[s.find('e')+1:s.find(')')]) + ","
  Cstr = Cstr[:-1]
  Clist = Cstr.split(',')
  if not '' in Clist: Clist.sort(key=int)
  Cstr = ','.join(Clist)
  return Cstr

def idpl2plnames(markidC):
  markidC = markidC[:-1].split(",")
  markC = ""
  #print(model.PL)
  first = True
  for i in model.PL:
    for j in markidC:
      if first and model.PL[i]["id"] == int(j):
        markC += i
        first = False
      elif model.PL[i]["id"] == int(j): markC += "," + i
  tupleC = tuple(markC.split(","))
  return tupleC

def sort_by_number(string):
  number = int(string.split(',')[-1][1:].strip(')'))
  return number

outf = f"{script_dir}/{os.path.dirname(model_ll)}/all_confs-to-marking_{base_output}.evco"
with open(outf, "w") as fout:
  for i in wl:
    listC = str_conf(i).split(',')
    for ci in range(len(listC)):
      if ','.join(listC[:ci+1]) in known: break
      check = set(idpl2plnames(subprocess.check_output([
        "mci2asp", "-cf", ','.join(listC[:ci+1]), mci]).decode())) == \
        set(bad_markings[0])
      if check:
        known.add(','.join(listC[:ci+1]))
        #print(sorted(i, key=sort_by_number))
        print(' '.join(listC[:ci+1])+' 0', file=fout)
        break

