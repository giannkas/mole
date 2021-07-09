#include "common.h"
#include "unfold.h"
#include <string.h>

/*****************************************************************************/

/* The worklist of possible extensions is organized as a priority heap
   using an array (of pointers). The array is extended in steps of size
   PE_ALLOC_STEP as needed.						*/

#define PE_ALLOC_STEP 1024
pe_queue_t **pe_queue;		/* the priority array */
int pe_qsize, pe_qalloc;	/* current/maximum capacity */

/* This structure (a list of node lists) is used during the search for
   possible extensions to enumerate all potential sets conditions for a
   given transition.							*/
typedef struct pe_comb_t
{
	nodelist_t *current;
	nodelist_t *start;
} pe_comb_t;

pe_comb_t *pe_combs;	/* used in pe() */
cond_t   **pe_conds;	/* array of conditions, given by pe() to pe_insert() */
uchar     *pe0_conflicts;	/* conflicts of the initial conditions */

/*****************************************************************************/
/* Simple functions: initialize queue, release a queue entry, and release    */
/* memory allocated during initialization.				     */

void pe_init (nodelist_t *m0)
{
	int i;

	pe_qsize = 0;
	pe_queue = MYmalloc((pe_qalloc = PE_ALLOC_STEP) * sizeof(pe_queue_t*));
	
	pe_conds = MYmalloc((net->maxpre + net->maxres) * sizeof(place_t*));
	pe_combs = MYmalloc((net->maxpre + net->maxres) * sizeof(pe_comb_t));

	//printf("net->maxpre: %d, net->maxres: %d\n", net->maxpre, net->maxres);
	/* determine size of initial marking */
	for (i = 0; m0; m0 = m0->next) i++;
	pe0_conflicts = MYcalloc((i + 8) / 8);
	//printf("pe0_conflicts: %u, i: %d\n", *pe0_conflicts, i);
}

void pe_free (pe_queue_t *qu)
{
	free(qu->conds);
	free(qu);
}

void pe_finish ()
{
	free(pe_conds);
	free(pe0_conflicts);
	free(pe_combs);
}

/*****************************************************************************/
/* Adds the possible extension (tr,pe_conds) to the priority queue.	     */

void pe_insert (trans_t *tr)
{
	pe_queue_t *qu_new = create_queue_entry(tr);
	
	int index = ++pe_qsize;
	static char stoptr_found = 0;
	/* If -d is used, ignore the new event if its size exceeds the limit. */
	if (unfold_depth && qu_new->lc_size > unfold_depth)
		{	pe_qsize--; return;	}
	
	/* When the -T is used and stoptr is found, empty the queue to make
	   sure that the corresponding event is processed immediately. Also,
	   prevent any further additions to the PE queue. */
	if (tr == stoptr)
	{
		while (--index) pe_free(pe_queue[index]);
		pe_queue[pe_qsize = 1] = qu_new;
		stoptr_found = 1;
	}
	else if (stoptr_found)
	{
		pe_qsize--;
		pe_free(qu_new); return;
	}

	if (pe_qsize >= pe_qalloc)
	{
		pe_qalloc += PE_ALLOC_STEP;
		pe_queue = MYrealloc(pe_queue,pe_qalloc * sizeof(pe_queue_t*));
	}

	/* insert new element at the end, then move upwards as needed */
	for (; index > 1; index /= 2)
	{
		if (pe_compare(qu_new,pe_queue[index/2]) > 0) break;
		pe_queue[index] = pe_queue[index/2]; /* move parent downwards */
	}
	pe_queue[index] = qu_new;
}

/*****************************************************************************/
/* Remove the minimal event from the queue and restore order.		     */

pe_queue_t* pe_pop (int where)
{
	pe_queue_t *first = pe_queue[where];
	/* printf("Trans associated: %s\n", first->trans->name);
	int size_preset = first->trans->preset_size;
	printf("Size preset: %d\n", size_preset);
	for (int i = 0; i < size_preset; i++)
		printf("Cond %d associated: %s\n", i, first->conds[i]->origin->name); */
	pe_queue_t *last;
	int index = where, newindex;

	if (!pe_qsize) return NULL;

	last = pe_queue[pe_qsize--];
	for (;;)	/* sift last element downwards */
	{
		if (index > pe_qsize / 2) break;
		/* compare "last" and children of index */
		if (index*2 < pe_qsize
			&& pe_compare(last,pe_queue[index*2+1]) > 0)
		{
			if (pe_compare(pe_queue[index*2],pe_queue[index*2+1])>0)
				newindex = index*2 + 1;
			else
				newindex = index*2;
		}
		else if (pe_compare(last,pe_queue[index*2]) > 0)
			newindex = index * 2;
		else
			break;
		pe_queue[index] = pe_queue[newindex];	/* move child upwards */
		index = newindex;
	}
	pe_queue[index] = last;
	return first;
}

/*****************************************************************************/
/* Check whether any pair of conditions downwards from curr is in conflict   */
/* The check excludes the condition given to pe(), because we already know   */
/* that that one is not in conflict with any of the others.		     */

char pe_conflict (pe_comb_t *curr)
{
	int sz;
	cond_t *co, **co_ptr;
	event_t *ev, **queue;

	/* just one condition - no conflict */
	if (curr == pe_combs) return 0;

	++ev_mark;
	*(queue = events) = NULL;

	/* put the pre-events into the queue */
	while (curr >= pe_combs)
	{
		(co = (curr--)->current->node)->mark = ev_mark;
		if ((ev = co->pre_ev) && ev->mark != ev_mark)
			 (*++queue = ev)->mark = ev_mark;
	}

	/* go upwards, try to find two paths converging at some condition */
	/* Check later how it would work if there is an asymmetric conflict
	with reset and production arcs */
	while ((ev = *queue))
	{
		queue--;
		for (sz = ev->origin->prereset_size, co_ptr = ev->preset; sz--; )	//*** NEW  ***//
		{
			if ((co = *co_ptr++)->mark == ev_mark) return 1;
			co->mark = ev_mark;
			if ((ev = co->pre_ev) && ev->mark != ev_mark)
				 (*++queue = ev)->mark = ev_mark;
		}
	}

	return 0;
}

/*****************************************************************************/
/* Find the new possible extensions created by the addition of co.	     */

void pe (cond_t *co)
{
	nodelist_t *pl_post, *tr_pre, **compat_conds;
	pe_comb_t *curr_comb;
	cond_t **cocoptr;
	place_t *pl = co->origin, *pl2;
	trans_t *tr;
	event_t *ev = co->pre_ev;
	
	*pe_conds = co;	/* any new PE contains co */
	nodelist_push(&(pl->conds),co);
	
	/* check the transitions in pl's postset */
	//for (pl_post = pl->postset; pl_post && !nodelist_find(&((tr = pl_post->node)->reset),pl); pl_post = pl_post->next)
	for (pl_post = nodelist_concatenate(pl->postset, pl->reset); pl_post; pl_post = pl_post->next) 		//*** NEW  ***//
	{
		if (!ev && pl->marked == 0 && nodelist_find(pl->postset, pl_post->node)){
			printf("pl name forbiden to compute possible extensions: %s\n", pl->name);
			printf("tr name forbiden to compute possible extensions: %s\n", ((trans_t*)(pl_post->node))->name);
			print_marking(pl->postset);
			printf("\n");
		}
		/* else{
			printf("conditions associated of transition: %s\n", ev->origin->name);
			cond_t *co2, **co_ptr;
			int i;
			for (i = ev->preset_size, co_ptr = ev->preset; i--;)
			{				
				printf("c%d\n",(co2 = *co_ptr)->mark);
				co_ptr++;
			}			
		} */
		if ((ev && nodelist_find(pl->postset, pl_post->node) && 
			nodelist_find(ev->origin->reset, pl) &&
			!nodelist_find(ev->origin->postset, pl)) ||
			(!ev && pl->marked == 0 && nodelist_find(pl->postset, pl_post->node))
			){
			break;
		}
		/* if ((ev && nodelist_find(pl->postset, pl_post->node) &&
			strcmp(pl->name, "P2") != 0 && 
			strcmp(pl->name, "P3") != 0 &&
			1 &&
			1
			//!nodelist_find(ev->origin->postset, pl)
			)
			||
			(0)
			//(!ev && pl->marked == 0 && nodelist_find(pl->postset, pl_post->node))
			){
			// 
			// Check whether it's marked and the corresponding events belong to 
			// the postset.
			break;
		} */
		
		tr = pl_post->node;
		//if (strcmp(pl->name, "P2") == 0 && !pl->reset) printf("hola\n");
		/* nodelist_t *ptr0 = tr->reset;
		while (ptr0) {
			if (strcmp(tr->name, "T0") == 0)
				printf("R_%s, ", ((place_t*)(ptr0->node))->name);
			ptr0 = ptr0->next;
		}
		printf("\n"); */
		(curr_comb = pe_combs)->start = NULL;

		/* for every other post-place of tr, collect the conditions
			that are co-related to co in the comb structure */
		//for (tr_pre = tr->preset; tr_pre; tr_pre = tr_pre->next) 	//*** NEW  ***//
		for (tr_pre = nodelist_concatenate(tr->reset, tr->preset); tr_pre; tr_pre = tr_pre->next) 	//*** NEW  ***//
		{
			//nodelist_t *ptr = tr_pre;
			//printf("List of conditions in the preset or reset set of transition %s: \n", ((trans_t*)(pl_post->node))->name);
			
			/* while (ptr) {
				if (strcmp(pl->name, "P2") == 0)
					printf("%s, ", ((place_t*)(ptr->node))->name);
				ptr = ptr->next;
			} */
			if ((pl2 = tr_pre->node) == pl) continue;

			compat_conds = &(curr_comb->start);
			cocoptr = co->co_common.conds - 1;
			//if (strcmp(pl->name, "P2") == 0) 
			//	printf("cocoptr->origin: %s\n", cocoptr[0]->origin->name);
			while (*++cocoptr){
				if ((*cocoptr)->origin == pl2){
					nodelist_push(compat_conds,*cocoptr);
				}
			}
			cocoptr = co->co_private.conds - 1;
			while (*++cocoptr){
				if ((*cocoptr)->origin == pl2){
					nodelist_push(compat_conds,*cocoptr);
				}
			}
			
			if (!*compat_conds) break;

			curr_comb->current = curr_comb->start;
			(++curr_comb)->start = NULL;
		}
		
		
		/* find all non-conflicting combinations in the comb */
		curr_comb = pe_combs;
		/* printf("curr_comb->start: %s\n",((cond_t*)(curr_comb->start->node))->origin->name);
		printf("curr_comb->current: %s\n",((cond_t*)(curr_comb->current->node))->origin->name); */
		/* if (curr_comb->start && curr_comb->current)
		{
			printf("curr_comb->start: %s\n",((cond_t*)(curr_comb->start->node))->origin->name);
			printf("curr_comb->current: %s\n",((cond_t*)(curr_comb->current->node))->origin->name);
		} */
				
		if (!tr_pre) while (curr_comb >= pe_combs)
		{	
			if (!curr_comb->start)
			{
				cond_t **co_ptr = pe_conds;
				for (curr_comb = pe_combs; curr_comb->start;
						curr_comb++)
					*++co_ptr = curr_comb->current->node;
				pe_insert(tr); // CHECK pe_insert!!
				
				curr_comb--;
			}
			else if (!pe_conflict(curr_comb))
			{
				curr_comb++;
				continue;
			}
			
			while (curr_comb >= pe_combs && !(curr_comb->current =
						curr_comb->current->next))
			{
				curr_comb->current = curr_comb->start;
				curr_comb--;
			}
		}
		
		/* release the comb lists */
		for (curr_comb = pe_combs; curr_comb->start; curr_comb++)
			nodelist_delete(curr_comb->start);
		
	}
	
}
