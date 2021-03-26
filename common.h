/****************************************************************************/
/* common.h								    */
/*									    */
/* Definitions for common.c						    */
/****************************************************************************/

#ifndef __COMMON_H__
#define __COMMON_H__

#include <stdlib.h>
#include <assert.h>

#define PROGRAM_NAME "unfold"

extern void* MYmalloc(size_t);
extern void* MYcalloc(size_t);
extern void* MYrealloc(void*,size_t);
extern char* MYstrdup(char*);
extern void nc_error (const char*,...);
extern void nc_warning (const char*,...);
extern float get_seconds ();

#endif
