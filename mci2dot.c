#include <string.h>
#include <stdio.h>
#include <stdlib.h>

typedef struct cut_t
{
  int repeat;
  int szcut, szevscut;
  int *cut;
  int *evscut;
} cut_t;

int read_mci_file (char *mcifile, char *evcofile, int m_repeat, char* evname)
{
  #define read_int(x) fread(&(x),sizeof(int),1,mcif)

  FILE *mcif, *evcof;
  int nqure, nqure_, nquszcut, nquszevscut, szcuts, 
    numco, numev, numpl, numtr, sz, i, value;
  int pre_ev, post_ev, cutoff, harmful, dummy = 0;
  int *co2pl, *ev2tr, *tokens, *queries_co,
   *queries_ev, *cutoffs, *harmfuls;
  char **plname, **trname, *c;
  cut_t **cuts;

  if (!(mcif = fopen(mcifile,"rb")))
  {
    fprintf(stderr,"cannot read file %s\n",mcifile);
    exit(1);
  }

  if (evcofile)
  {
    if (!(evcof = fopen(evcofile, "r")))
    {
      fprintf(stderr,"cannot read file %s\n",evcofile);
      exit(1);
    }
  }

  if(!evname) 
    printf("digraph test {\n");

  read_int(numco);
  read_int(numev);

  co2pl = malloc((numco+1) * sizeof(int));
  tokens = malloc((numco+1) * sizeof(int));
  queries_co = malloc((numco+1) * sizeof(int));
  queries_ev = malloc((numev+1) * sizeof(int));
  ev2tr = malloc((numev+1) * sizeof(int));
  cutoffs = calloc(numev+1, sizeof(int));
  harmfuls = calloc(numev+1, sizeof(int));

  read_int(nqure);
  nqure_ = abs(nqure);
  cuts = calloc((szcuts = nqure_+1), sizeof(cut_t*));
  if(nqure_ && m_repeat > 0 && m_repeat <= nqure_) 
    dummy = 1;
  while(nqure_)
  {
    read_int(nquszcut);
    read_int(nquszevscut);
    cuts[nqure_] = malloc(sizeof(cut_t));
    cuts[nqure_]->repeat = nqure;
    cuts[nqure_]->szcut = nquszcut;
    cuts[nqure_]->szevscut = nquszevscut;
    cuts[nqure_]->cut = calloc(nquszcut+1, sizeof(int));
    cuts[nqure_]->evscut = calloc(nquszevscut+1, sizeof(int));
    for (i = 1; i <= nquszcut; i++)
      read_int(cuts[nqure_]->cut[i]);
    for (i = 1; i <= nquszevscut; i++)
      read_int(cuts[nqure_]->evscut[i]);
    read_int(nqure);
    nqure_ = abs(nqure);
  }

  for (i = 1; i <= numev; i++){
    read_int(ev2tr[i]);
    read_int(queries_ev[i]);
    if (evcofile) queries_ev[i] = 0;
  }

  for (i = 1; i <= numco; i++)
  {
    read_int(co2pl[i]);
    read_int(tokens[i]);
    read_int(queries_co[i]);
    if (evcofile) queries_co[i] = 0;
    read_int(pre_ev);
    if (pre_ev && !evname) printf("  e%d -> c%d;\n",pre_ev,i);
    do {
      read_int(post_ev);
      if (post_ev && !evname) printf("  c%d -> e%d;\n",i,post_ev);
    } while (post_ev);
  }

  if(dummy && !evcofile)
  {
    if (cuts[m_repeat] && cuts[m_repeat]->repeat < 0)
    {
      memset(queries_ev,0,(numev)*sizeof(int));
      memset(queries_co,0,(numco)*sizeof(int));
      for (i = 1; i <= cuts[m_repeat]->szcut; i++)
        queries_co[cuts[m_repeat]->cut[i]] = 1;
      for (i = 1; i <= cuts[m_repeat]->szevscut; i++)
        queries_ev[cuts[m_repeat]->evscut[i]] = 1;
    }
  }

  for (;;) {
    read_int(harmful);
    if (!harmful) break;
    harmfuls[harmful] = harmful;
  }

  for (;;) {
    read_int(cutoff);
    if (!cutoff) break;
    cutoffs[cutoff] = cutoff;
#ifdef CUTOFF
    printf("  e%d [style=filled];\n",cutoff);
#endif
    read_int(dummy);
#ifdef CUTOFF
    printf("  e%d [style=dashed];\n",dummy);
#endif
  }

  do { read_int(dummy); } while(dummy);
  read_int(numpl);
  read_int(numtr);
  read_int(sz);

  plname = malloc((numpl+2) * sizeof(char*));
  trname = malloc((numtr+2) * sizeof(char*));

  for (i = 1; i <= numpl+1; i++) plname[i] = malloc(sz+1);
  for (i = 1; i <= numtr+1; i++) trname[i] = malloc(sz+1);

  for (c = plname[i=1]; i <= numpl; c = plname[++i])
    do { fread(c,1,1,mcif); } while (*c++);
  fread(c,1,1,mcif);

  for (c = trname[i=1]; c = trname[i], i <= numtr; c = trname[++i])
    do { fread(c,1,1,mcif); } while (*c++);
  fread(c,1,1,mcif);

  char color1[] = "#ccccff"; // or "lightblue";
  char color2[] = "gold";
  char color3[] = "orange";
  char color4[] = "#cce6cc"; // or "palegreen";
  char color5[] = "cornflowerblue";
  char color6[] = "black";
  char color7[] = "firebrick2";
  char color8[] = "#4040ff";
  char color9[] = "#409f40";

  dummy = 0;
  while (fscanf(evcof," %d",&value) != EOF)
  {
    if (value != 0 && !dummy)
      queries_ev[value] = 1;
    else
      {queries_co[value] = 1; dummy = 1;}
  }

  int found = 0;
  if(!evname)
  {
    for (i = 1; i <= numco; i++)
      printf("  c%d [color=\"%s\" fillcolor=\"%s\" label= <%s<FONT COLOR=\"red\"><SUP>%d</SUP></FONT>&nbsp;(c%d)> shape=circle style=filled];\n",
          i,color8,queries_co[i] ? color2 : color1,plname[co2pl[i]],tokens[i],i);
    for (i = 1; i <= numev; i++)
      if (i == cutoffs[i])
        printf("  e%d [color=%s fillcolor=%s label=\"%s (e%d)\" shape=box style=filled];\n",
            i,queries_ev[i] ? color3 : color6,color5,trname[ev2tr[i]],i);
      else if ( i == harmfuls[i])
        printf("  e%d [color=%s fillcolor=%s label=\"%s (e%d)\" shape=box style=filled];\n",
            i,queries_ev[i] ? color3 : color6,color7,trname[ev2tr[i]],i);
      else
        printf("  e%d [color=\"%s\" fillcolor=\"%s\" label=\"%s (e%d)\" shape=box style=filled];\n",
            i,queries_ev[i] ? color6 : color9,queries_ev[i] ? color3 : color4,trname[ev2tr[i]],i);
    printf("}\n");
  }
  else{
    for (i = 1; i <= numev && !found && evname; i++)
      if (!strcmp(trname[ev2tr[i]], evname))
        found = 1;
  }

  fclose(mcif);
  fclose(evcof);
  return found;
}

int main (int argc, char **argv)
{
  int i, m_repeat = 0;
  char *mcifile = NULL, *evcofile = NULL, *evname = NULL;

  for (i = 1; i < argc; i++)
    if (!strcmp(argv[i],"-r"))
      m_repeat = atoi(argv[++i]);
    else if (!strcmp(argv[i],"-reach"))
      evname = argv[++i];
    else if(!mcifile)
      mcifile = argv[i];
    else
      evcofile = argv[i];

  if (!mcifile)
  {
    fprintf(stderr,"usage: mci2dot [options] <mcifile> <evcofile>\n\n"

    "     Options:\n"
    "      -r <instance>  highlight <instance> of a repeated marking\n"
    "      -reach <evname>  if used, it will look for an event related to an attractor to return whether such event was found\n\n"

    "<evcofile> is an optional file whose first line contains\n"
    "the IDs of a firing sequence of events and the second line\n"
    "represents IDs of conditions in the cut.\n\n");
    exit(1);
  }
  exit(!read_mci_file(mcifile, evcofile, m_repeat, evname));
}
