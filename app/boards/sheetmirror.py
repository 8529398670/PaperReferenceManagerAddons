"""A list as a Google Sheet grid , and a Google Sheet grid back as /sort ops --
the pure half of the Sheets mirror ( app/boards/sheetsync.py does the I/O ).
Ported from the old prma src/db/sheetmirror.py as it was.

The sheet is one tab , one row per paper on the list , in YOUR order :

  Key | # | DOI | Title | Year | Authors | Journal | Tags | <the board's columns>

Key is the row's board key -- hidden and warning-protected on the sheet , and
the only thing a row is matched by. # is the position , rewritten on every push
and ignored when read back ( the ROW ORDER is the order ). Tags are one cell ,
comma-separated. The staging shelf isn't mirrored.

Two-way reading compares the sheet with the grid as it was last pushed ( the
BASE ) , never with the board : what changed in the sheet is what someone typed
there , and only that becomes ops ( app/boards/ops.py ) -- run against the
board as it is NOW , so an edit made on the board meanwhile is kept.

  a changed DOI / Title / Year / Authors / Journal   -> update
  a changed column cell                              -> set_cell
  a changed Tags cell                                -> tag ( add / remove )
  a row with no Key but a DOI or Title               -> add , where it sits
  a Key that was pushed and is gone                  -> remove
  a header added / renamed / removed                 -> column_add / _rename / _delete
  columns dragged into another order                 -> column_move , each in turn
  rows dragged into another order                    -> move , only the rows that
                                                        left the longest run still in
                                                        the old order ( so only they
                                                        are marked placed )
"""

import bisect
import re

from . import ops as sortops

FIXED = [ ( "key" , "Key" ) , ( "pos" , "#" ) , ( "doi" , "DOI" ) , ( "title" , "Title" ) ,
	( "year" , "Year" ) , ( "authors" , "Authors" ) , ( "journal" , "Journal" ) , ( "tags" , "Tags" ) ]
DETAILS = ( "doi" , "title" , "year" , "authors" , "journal" )   # what `update` takes
FIXED_LABELS = { lab.lower() for _ , lab in FIXED }
SPARE_ROWS = 20   # blank rows left under the list , for typing new papers into
SPARE_COLS = 2    # ... and blank columns , for a new one


class Refused( Exception ):
	"""The sheet doesn't look like something to read back ( a missing header ,
	most of the list gone at once ). Nothing is applied ; the message says why."""


def norm( v ):
	"""One cell as text -- what both sides of a comparison are reduced to."""
	if v is None:
		return ""
	if isinstance( v , bool ):
		return "TRUE" if v else "FALSE"
	if isinstance( v , float ) and v.is_integer():
		return str( int( v ) )
	return str( v ).replace( "\r\n" , "\n" ).replace( "\r" , "\n" ).strip()


def split_tags( s ):
	out , seen = [] , set()
	for t in re.split( r"[,;\n]" , norm( s ) ):
		t = t.strip()
		if t and t.lower() not in seen:
			seen.add( t.lower() )
			out.append( t )
	return out


# ---------------------------------------------------------------------------
# board -> sheet
# ---------------------------------------------------------------------------

def _authors( v ):
	return "; ".join( map( str , v ) ) if isinstance( v , list ) else norm( v )


def grid( doc , meta=None ):
	"""The list as the sheet shows it -> { rows , colmap }. `rows` is the header
	plus one row per paper ( Year a number , everything else text ) ; `colmap`
	is header text -> "fixed:<field>" / "col:<column id>" , how a header reads
	back. A board column whose label clashes with a fixed header ( or another
	column's ) is written with its id after it , so every header is unique."""
	meta   = meta or {}
	cols   = doc.get( "columns" ) or []
	header , colmap = [] , {}
	for f , lab in FIXED:
		header.append( lab )
		colmap[ lab ] = f"fixed:{f}"
	for c in cols:
		lab = str( c.get( "label" ) or c[ "id" ] ).strip()
		if lab.lower() in { h.lower() for h in header }:
			lab = f"{lab} ({c[ 'id' ]})"
		header.append( lab )
		colmap[ lab ] = f"col:{c[ 'id' ]}"
	rows = [ header ]
	for i , it in enumerate( doc.get( "items" ) or [] ):
		m    = meta.get( it[ "key" ] ) or {}
		year = it.get( "year" ) or m.get( "year" ) or ""
		doi  = it.get( "doi" ) or m.get( "doi" ) or ""
		f    = it.get( "fields" ) or {}
		rows.append( [ it[ "key" ] , i + 1 , doi , it.get( "title" ) or m.get( "title" ) or "" ,
			year if isinstance( year , int ) else norm( year ) ,
			_authors( it.get( "authors" ) ) , it.get( "journal" ) or "" ,
			", ".join( it.get( "tags" ) or [] ) ]
			+ [ norm( f.get( c[ "id" ] ) ) for c in cols ] )
	return { "rows": rows , "colmap": colmap }


def padded( rows , nrows , ncols ):
	"""`rows` filled out with "" to nrows x ncols -- written whole , so whatever
	was in the sheet past the list ( rows since deleted , a stray note ) is
	cleared by the same call."""
	out = [ list( r ) + [ "" ] * ( ncols - len( r ) ) for r in rows ]
	out += [ [ "" ] * ncols for _ in range( nrows - len( out ) ) ]
	return out


# ---------------------------------------------------------------------------
# sheet -> board
# ---------------------------------------------------------------------------

def _parse( rows , colmap ):
	"""A grid -> ( header , [ ( key , { field: text } ) , ... ] ) , with the
	headers this colmap doesn't know reported as ( "new" , text ). Blank rows
	are dropped ; so is a second row carrying a Key already seen ( a pasted
	copy ) , which keeps it from becoming a duplicate."""
	if not rows:
		raise Refused( "the sheet is empty -- not even a header row" )
	head = [ norm( h ) for h in rows[ 0 ] ]
	if "Key" not in head:
		raise Refused( "the sheet has no Key column ( its header row was changed or removed )" )
	where = []
	for h in head:
		where.append( colmap.get( h ) or ( ( "new:" + h ) if h else None ) )
	out , seen = [] , set()
	for r in rows[ 1: ]:
		vals = {}
		for j , tgt in enumerate( where ):
			if tgt and not tgt.startswith( "new:" ):
				vals[ tgt ] = norm( r[ j ] ) if j < len( r ) else ""
		new = { tgt[ 4: ]: norm( r[ j ] ) for j , tgt in enumerate( where )
			if tgt and tgt.startswith( "new:" ) and j < len( r ) and norm( r[ j ] ) }
		key = vals.get( "fixed:key" , "" )
		if not key and not any( v for k , v in vals.items() if k != "fixed:pos" ) and not new:
			continue
		if key:
			if key in seen:
				continue
			seen.add( key )
		out.append( ( key , vals , new ) )
	return head , where , out


def _lis_keep( seq ):
	"""Indices of one longest strictly increasing subsequence of `seq`."""
	tails , tvals , prev , idx = [] , [] , [ None ] * len( seq ) , []
	for i , v in enumerate( seq ):
		j = bisect.bisect_left( tvals , v )
		if j:
			prev[ i ] = tails[ j - 1 ]
		if j == len( tails ):
			tails.append( i )
			tvals.append( v )
		else:
			tails[ j ] , tvals[ j ] = i , v
	k = tails[ -1 ] if tails else None
	while k is not None:
		idx.append( k )
		k = prev[ k ]
	return set( idx )


def diff( base , sheet , max_remove=25 ):
	"""What was typed into the sheet since `base` ( grid()'s answer as pushed )
	-> ops for sheetmirror.apply , in the order they must run : columns ,
	removals , edits , additions , moves. `sheet` is the grid as read back.
	Refused when the sheet is unreadable or would take more than `max_remove`
	rows off the list in one go ( a cleared tab , a sort-and-delete gone wrong )."""
	colmap = base[ "colmap" ]
	_ , _ , was = _parse( base[ "rows" ] , colmap )
	head , where , now = _parse( sheet , colmap )
	lost = [ lab for f , lab in FIXED if f not in ( "key" , "pos" ) and lab not in head ]
	if lost:
		# A retyped fixed header would read back as a NEW column full of titles.
		raise Refused( f"the sheet's {', '.join( lost )} header was changed or removed -- put it back" )
	was_by = { k: v for k , v , _ in was }
	ops = []

	# -- columns : known headers that vanished , and new ones -------------------
	gone_cols = [ h for h , tgt in colmap.items() if tgt.startswith( "col:" ) and h not in head ]
	new_cols  = [ tgt[ 4: ] for tgt in where if tgt and tgt.startswith( "new:" ) ]
	new_cols  = [ h for h in new_cols if h.lower() not in FIXED_LABELS ]
	renamed   = {}
	if gone_cols and len( gone_cols ) == len( new_cols ):
		# As many headers went as came : the same columns , retyped.
		for old , new in zip( gone_cols , new_cols ):
			renamed[ new ] = colmap[ old ][ 4: ]
			ops.append( { "op": "column_rename" , "col": colmap[ old ][ 4: ] , "label": new } )
	else:
		for old in gone_cols:
			ops.append( { "op": "column_delete" , "col": colmap[ old ][ 4: ] } )
		for new in new_cols:
			ops.append( { "op": "column_add" , "label": new } )
	gone_ids = { colmap[ h ][ 4: ] for h in gone_cols } - set( renamed.values() )

	# -- the columns' order : the sheet's , when its columns were dragged about --
	# Known columns by id , new ones by label ( column_move finds either ) , in
	# the order the sheet shows them. Against the order they would have after
	# the ops above ( the old ones as pushed , new ones added at the end ) ; only
	# when the two differ is every column moved , so an untouched sheet is no op.
	sheet_order = []
	for tgt in where:
		if not tgt:
			continue
		if tgt.startswith( "col:" ):
			if tgt[ 4: ] not in gone_ids:
				sheet_order.append( tgt[ 4: ] )
		elif tgt.startswith( "new:" ) and tgt[ 4: ].lower() not in FIXED_LABELS:
			sheet_order.append( renamed.get( tgt[ 4: ] , tgt[ 4: ] ) )
	was_order = [ tgt[ 4: ] for h , tgt in colmap.items() if tgt.startswith( "col:" ) ]
	expect = [ c for c in was_order if c in sheet_order ] + [ c for c in sheet_order if c not in was_order ]
	if sheet_order != expect:
		ops += [ { "op": "column_move" , "col": c , "to": i + 1 } for i , c in enumerate( sheet_order ) ]

	def cells_of( vals , extra ):
		"""{ column id or label: text } for one sheet row ( new headers by label )."""
		out = { tgt[ 4: ]: v for tgt , v in vals.items() if tgt.startswith( "col:" ) }
		for lab , v in extra.items():
			out[ renamed.get( lab , lab ) ] = v
		return out

	# -- rows taken off ------------------------------------------------------
	have    = { k for k , _ , _ in now if k }
	removed = [ k for k , _ , _ in was if k not in have ]
	if len( removed ) > max_remove:
		raise Refused( f"the sheet is missing {len( removed )} of the {len( was )} papers -- more than "
			f"max_remove ( {max_remove} ) , so nothing was read back. Delete them on the board , "
			"or raise max_remove in config.yaml" )
	# One op each : a row already gone from the board fails alone.
	ops += [ { "op": "remove" , "rows": [ k ] } for k in removed ]

	# -- edits to rows that were there -----------------------------------------
	for key , vals , extra in now:
		old = was_by.get( key )
		if old is None:
			continue
		upd = { f: vals.get( f"fixed:{f}" , "" ) for f in DETAILS
			if f"fixed:{f}" in vals and vals[ f"fixed:{f}" ] != old.get( f"fixed:{f}" , "" ) }
		if upd:
			ops.append( { "op": "update" , "row": key , **upd } )
		if "fixed:tags" in vals and vals[ "fixed:tags" ] != old.get( "fixed:tags" , "" ):
			a = { t.lower(): t for t in split_tags( vals[ "fixed:tags" ] ) }
			b = { t.lower(): t for t in split_tags( old.get( "fixed:tags" , "" ) ) }
			add , rem = [ a[ t ] for t in a if t not in b ] , [ b[ t ] for t in b if t not in a ]
			if add or rem:
				ops.append( { "op": "tag" , "row": key , "add": add , "remove": rem } )
		for cid , v in cells_of( vals , extra ).items():
			if cid in gone_ids:
				continue
			if v != old.get( f"col:{cid}" , "" ):
				ops.append( { "op": "set_cell" , "row": key , "col": cid , "value": v } )

	# -- new rows , and where everything sits ----------------------------------
	base_pos = { k: i for i , ( k , _ , _ ) in enumerate( was ) }
	kept     = [ ( k , _ ) for k , _ , _ in now if k in base_pos ]
	stay     = _lis_keep( [ base_pos[ k ] for k , _ in kept ] )
	moved    = { k for n , ( k , _ ) in enumerate( kept ) if n not in stay }
	prev , n_new = None , 0
	for key , vals , extra in now:
		if key in base_pos:
			if key in moved:
				ops.append( { "op": "move" , "row": key , "to": { "after": prev } if prev else "top" } )
			prev = key
			continue
		doi   = vals.get( "fixed:doi" , "" )
		title = vals.get( "fixed:title" , "" )
		if not ( key or doi or title ):
			continue
		obj = { k: vals.get( f"fixed:{k}" , "" ) for k in DETAILS if vals.get( f"fixed:{k}" ) }
		if obj.get( "year" , "" ).isdigit():
			obj[ "year" ] = int( obj[ "year" ] )
		else:
			obj.pop( "year" , None )
		if key:
			obj[ "key" ] = key
		op = { "op": "add" , "paper": key or doi or title , "fallback": obj ,
			"at": { "after": prev } if prev else "top" , "if_absent": True }
		tags = split_tags( vals.get( "fixed:tags" , "" ) )
		if tags:
			op[ "tags" ] = tags
		cells = { k: v for k , v in cells_of( vals , extra ).items() if v and k not in gone_ids }
		if cells:
			op[ "cells" ] = cells
		op[ "ref" ] = f"@new{n_new}"
		ops.append( op )
		prev , n_new = f"@new{n_new}" , n_new + 1
	return ops


def apply( doc , ctx , ops ):
	"""Run diff()'s ops against `doc` ( in place ) one at a time , carrying on
	past one that fails -- a sheet typo shouldn't hold up every other edit , and
	the next push puts the board's value back over it. -> ( applied , errors ).

	Two things only these ops carry : an `add` names a `fallback` paper object
	for when its DOI / title isn't found in the library , and a `ref`
	( "@newN" ) that later ops anchor to before its key is known."""
	refs , applied , errors = {} , 0 , []

	def sub( v ):
		if isinstance( v , str ):
			return refs.get( v , v )
		if isinstance( v , dict ):
			return { k: sub( x ) for k , x in v.items() }
		return v
	for op in ops:
		op = dict( op )
		fallback , ref = op.pop( "fallback" , None ) , op.pop( "ref" , None )
		op = { k: sub( v ) for k , v in op.items() }
		if any( isinstance( v , str ) and v.startswith( "@new" ) for v in ( op.get( "row" ) ,
				( op.get( "at" ) or {} ).get( "after" ) if isinstance( op.get( "at" ) , dict ) else None ,
				( op.get( "to" ) or {} ).get( "after" ) if isinstance( op.get( "to" ) , dict ) else None ) ):
			# Anchored to a new row that couldn't be added : land it at the end.
			op[ "at" if "at" in op else "to" ] = "bottom"
		try:
			try:
				res = sortops.apply_op( doc , ctx , op )
			except sortops.OpError:
				if not fallback or op.get( "op" ) != "add":
					raise
				res = sortops.apply_op( doc , ctx , { **op , "paper": fallback } )
			applied += 1
			if ref and res and res.get( "key" ):
				refs[ ref ] = res[ "key" ]
		except sortops.OpError as e:
			errors.append( f"{op.get( 'op' )} {op.get( 'row' ) or op.get( 'paper' ) or op.get( 'col' ) or ''} : {e}" )
	return applied , errors
