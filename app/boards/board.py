# Ported from the old prma src/db/sortboard.py: the board rules, unchanged. Re-indented,
# its imports pointed here, and its file storage left behind (boards live in
# the database now: app/boards/store.py).
"""
The sort board : one hand-curated , hand-ordered list of papers ( /sort ).

The sibling of src/db/tiers.py , and the same kind of store -- one hand-typed
document , written whole , snapshotted on every replaced version -- but with no
grouping at all. There is ONE list. A paper's position in it is the sort ( row 1
is row 1 , and the page numbers them ) , and everything else you want to say
about a paper you say with TAGS : fMRI , EEG , both , premier , whatever you
invent. Tags never move a row on their own ; the page has an option for that ,
off by default , because a hand-made order is the point of the page.

Shape ( output/cache/sort.json ) :

  {
    "version": 1 ,
    "updated_at": "..." ,
    "options":  { "auto_move": false ,         # re-group a row when its tags change
                  "add_where": "bottom" ,      # where a paper added from search lands
                  "fold_cols": [ "code" ] ,    # columns the page can fold away
                  "dropped_cols": [] ,         # columns deleted here ( not re-added by sharing )
                  "sheet_url": "" ,            # the Google Sheet last imported from
                  "cite_style": "" ,           # CSL style for the rows' citations
                                               #   ( "" = config.yaml's default )
                  "sync": "two-way" } ,        # share tag / cell edits : two-way | one-way | off
    "columns":  [ { "id": "notes" , "label": "Notes" } , ... ] ,
    "items":    [ { "key": "10.1038/..." , "title": "..." , "doi": "..." ,
                    "wid": "W..." , "pdf": "" , "year": 2023 , "journal": "" ,
                    "tags": [ "fMRI" , "EEG" ] , "fields": { "notes": "..." } ,
                    "added_at": "..." } , ... ] ,
    "staging":  [ ... same rows , not in the list yet ... ] ,
    "vocab":    { "tags": [ { "name": "premier" , "color": "#cfe0fb" } , ... ] }
  }

`staging` is the shelf a reference list imported from a .docx / a paste lands on
( src/db/refparse.py ) : the same rows , OFF the list , so a bibliography can be
read and tagged before any of it is given a position. See src/db/tiers.py for
why it lives in the document rather than in the browser.

`vocab.tags` is the tag list the page's chips and autocomplete offer , each with
the colour its chips are drawn in. It is part of the DOCUMENT , not of any one
browser , so a tag invented mid-session is still there after a restart --
including one you invented and haven't put on a paper yet , and in the same
colour on every machine you open the board on. Its ORDER is the order the chip
bar draws them in and the order you dragged them into , for the same reason :
grouping related tags side by side is a judgement about the tags.

A row's `tags` are stored ALPHABETICAL ( see tiers._clean_list ) , so a paper's
chips read the same way every time you look at it.

Keys , columns , history and the write-whole contract are all exactly as
src/db/tiers.py describes them -- read that docstring first.

This is also the document of every OTHER sort list ( /sort/<slug> ) : the same
shape , the same functions , given a `slug` that points the paths at that list's
own directory ( src/db/sortlists.py ). Without one it is the main board.
"""

import re
import time

from app.boards import util as utils
from app.boards import tiers as tiers_db


VERSION      = 1
HISTORY_KEEP = 40


# ---------------------------------------------------------------------------
# Defaults + normalization
# ---------------------------------------------------------------------------

# The columns every list has unless they were deleted from it : Notes , and the
# three a paper's methods are written up in -- Code and Datasets fill themselves
# for a paper the scans found links for ( sortops.prefill ) , which only works
# when the list HAS them. ( id , label , folded away as extra , what else
# counts as it -- a "Dataset" column is Datasets , not a reason for a second ).
STANDARD_COLS = (
    ( "notes" ,           "Notes" ,           False , re.compile( r"^notes?$" , re.I ) ) ,
    ( "methods-summary" , "Methods summary" , True ,  re.compile( r"^methods?[-_ ]?summary$" , re.I ) ) ,
    ( "datasets" ,        "Datasets" ,        True ,  re.compile( r"^datasets?$" , re.I ) ) ,
    ( "code" ,            "Code" ,            True ,  re.compile( r"^code$" , re.I ) ) ,
)
MAX_COLUMNS = 16


def _standard_columns( columns , fold , dropped ):
    """Add the STANDARD_COLS `columns` lacks , in place , at the end -- skipping
    one deleted from this list ( `dropped` ) and stopping at the column cap. A
    folded one joins `fold` ( in place ) , so it arrives out of the way."""
    for cid , label , folded , pat in STANDARD_COLS:
        if cid in dropped or len( columns ) >= MAX_COLUMNS:
            continue
        if any( c[ "id" ] == cid or pat.match( c[ "id" ] ) or pat.match( c[ "label" ] ) for c in columns ):
            continue
        columns.append( { "id": cid , "label": label } )
        if folded and cid not in fold:
            fold.append( cid )


SYNC_MODES = ( "two-way" , "one-way" , "off" )


def sync_mode( v ):
    """options.sync -> one of SYNC_MODES. It was a bool once : true ( or nothing
    said ) is two-way , false is off."""
    if v is False:
        return "off"
    return v if v in SYNC_MODES else "two-way"


def default_doc():
    """A fresh , empty board."""
    return {
        "version":    VERSION ,
        "updated_at": "" ,
        "options":    { "auto_move": False , "add_where": "bottom" ,
                        "fold_cols": [ c for c , _ , f , _ in STANDARD_COLS if f ] } ,
        "columns":    [ { "id": c , "label": l } for c , l , _ , _ in STANDARD_COLS ] ,
        "items":      [] ,
        "staging":    [] ,
        "vocab":      { "tags": [] } ,
    }


# ---------------------------------------------------------------------------
# Sections : a tier board is a list with sections switched on
# ---------------------------------------------------------------------------
#
# doc[ "sections" ] is [] on a plain list. On a tier board it is the tiers , in
# order -- { id , label , desc , color , locked } -- with Unranked always there ,
# locked and last. Each row says which one it is in ( row[ "section" ] ) , and
# the rows are kept grouped in section order , so a row's number is still its
# place in the one list and everything that works on a list ( moving , the
# shelf , CSV , undo , versions ) works on a tier board unchanged. Its rank IN
# its tier is its place among that tier's rows.
#
# A row that arrives with no section ( added , imported , taken off the shelf )
# lands in the target section ( options.section_target , ◉ on the page ,
# Unranked unless one is armed ) ; one naming a section that is gone goes to
# Unranked.

UNRANKED       = tiers_db.STAGING_ID
UNRANKED_LABEL = tiers_db.STAGING_LABEL
UNRANKED_COLOR = "#8b94a3"
MAX_SECTIONS   = 30


def default_sections():
    """S , A , B , C , D and Unranked -- the old tier list's ramp."""
    out = [ { "id": i , "label": l , "desc": "" , "color": c , "locked": False }
        for i , l , c in tiers_db.DEFAULT_TIERS ]
    return out + [ unranked() ]


def unranked():
    return { "id": UNRANKED , "label": UNRANKED_LABEL , "desc": "Added but not ranked yet" ,
        "color": UNRANKED_COLOR , "locked": True }


def _clean_sections( raw ):
    """The sections , in order , Unranked last -- or [] ( no sections )."""
    if not isinstance( raw , list ) or not raw:
        return []
    out , seen , last = [] , set() , None
    for t in raw:
        if not isinstance( t , dict ):
            continue
        label = tiers_db._clean_str( t.get( "label" ) , 60 ).strip()
        sid   = tiers_db.slug( t.get( "id" ) or label , "tier" )
        while sid in seen:
            sid = f"{sid}-2"
        seen.add( sid )
        row = { "id": sid , "label": label or sid.upper() ,
            "desc": tiers_db._clean_str( t.get( "desc" ) , 400 ) ,
            "color": tiers_db._clean_str( t.get( "color" ) , 32 ) or UNRANKED_COLOR ,
            "locked": bool( t.get( "locked" ) ) or sid == UNRANKED }
        if sid == UNRANKED:
            last = row
        else:
            out.append( row )
    return out[ :MAX_SECTIONS - 1 ] + [ last or unranked() ]


def _place_in_sections( items , raws , sections , target ):
    """Give every row its section and group them in section order ( stable :
    within a section the rows keep their order ). In place."""
    ids = { t[ "id" ]: n for n , t in enumerate( sections ) }
    for row , raw in zip( items , raws ):
        sid = raw.get( "section" ) if isinstance( raw , dict ) else None
        if not sid:
            sid = target
        row[ "section" ] = sid if sid in ids else UNRANKED
    items.sort( key=lambda row: ids[ row[ "section" ] ] )


def _one_namespace( row ):
    """ONE tag namespace here , so a document that came through the tier page
    ( which keeps modalities in their own list ) keeps everything it was tagged
    with."""
    row[ "tags" ] = tiers_db._clean_list( ( row.get( "tags" ) or [] ) + ( row.get( "mods" ) or [] ) )
    row.pop( "mods" , None )
    return row


def normalize( doc ):
    """Coerce a posted document into the documented shape. Never raises -- see
    tiers.normalize for why that matters here."""
    if not isinstance( doc , dict ):
        return default_doc()
    opts    = doc.get( "options" ) if isinstance( doc.get( "options" ) , dict ) else {}
    fold    = list( opts.get( "fold_cols" ) ) if isinstance( opts.get( "fold_cols" ) , list ) else []
    drop    = opts.get( "dropped_cols" ) if isinstance( opts.get( "dropped_cols" ) , list ) else []
    columns = tiers_db._clean_columns( doc.get( "columns" ) , keep_notes=False )
    _standard_columns( columns , fold , { c for c in drop if isinstance( c , str ) } )
    col_ids = [ c[ "id" ] for c in columns ]
    # One key namespace across the list AND the shelf , so a staged row can never
    # shadow a placed one. The list is cleaned first : it wins.
    items , raws , seen_keys = [] , [] , set()
    for raw in ( doc.get( "items" ) or [] ):
        row = tiers_db._clean_item( raw , col_ids , seen_keys )
        if row:
            items.append( _one_namespace( row ) )
            raws.append( raw )
    sections = _clean_sections( doc.get( "sections" ) )
    target   = opts.get( "section_target" )
    if not any( t[ "id" ] == target for t in sections ):
        target = UNRANKED
    if sections:
        _place_in_sections( items , raws , sections , target )
    staging = [ _one_namespace( r ) for r in
        tiers_db._clean_staging( doc.get( "staging" ) , col_ids , seen_keys ) ]
    tags = tiers_db._clean_vocab( ( doc.get( "vocab" ) or {} ).get( "tags" ) , 400 )
    seen = { t[ "name" ].lower() for t in tags }
    # Every tag actually in use joins the vocabulary , so one that arrived on an
    # imported row is offered by the chips and survives the next restart too.
    for it in items + staging:
        for t in it[ "tags" ]:
            if t.lower() not in seen:
                seen.add( t.lower() )
                tags.append( { "name": t , "color": "" } )
    where = opts.get( "add_where" )
    sheet = tiers_db._clean_str( opts.get( "sheet_url" ) , 500 ).strip()
    style = tiers_db._clean_str( opts.get( "cite_style" ) , 120 ).strip()
    return {
        "version":    VERSION ,
        "updated_at": tiers_db._clean_str( doc.get( "updated_at" ) , 40 ) ,
        "options":    {
            "auto_move": bool( opts.get( "auto_move" ) ) ,
            # Where a paper added from search lands : the end of the list , the
            # top , or straight after the last row you placed by hand.
            "add_where": where if where in ( "bottom" , "top" , "placed" ) else "bottom" ,
            # The columns a Google Sheet import brought in ( Methods summary ,
            # Datasets , Code ) : wide enough that the page folds them away behind
            # one show / hide button rather than drawing them all the time.
            "fold_cols": [ c for c in col_ids if c in fold ] ,
            # The columns deleted from this list , so an edit shared from another
            # list ( src/db/sortsync.py ) doesn't bring one back. A column added
            # again under the same id is off it.
            "dropped_cols": list( dict.fromkeys( str( c )[ :60 ] for c in drop
                if isinstance( c , str ) and c and c not in col_ids ) )[ -50: ] ,
            # The sheet the last one came from , so the next import is one click.
            # Only ever a docs.google.com link -- see src/db/gsheet.py .
            "sheet_url": sheet if sheet.startswith( "https://docs.google.com/spreadsheets/" ) else "" ,
            # The CSL style this board's rows are cited in , by file name without
            # the extension ( src/db/cite.py ). Empty means config.yaml's
            # citation.style -- so a board only carries one once somebody picked
            # a different one for it. Not checked against the directory here :
            # the styles on disk are a server fact , not a document one , and
            # cite.resolve_style falls back to the default for a name that has
            # since been deleted.
            "cite_style": style ,
            # How this list shares tag and cell edits with the other lists
            # holding the same papers ( src/db/sortsync.py ) : two-way sends its
            # own and takes theirs , one-way only takes theirs -- a working copy
            # that follows the original without writing back to it -- and off
            # does neither. Two-way unless somebody chose otherwise.
            "sync": sync_mode( opts.get( "sync" ) ) ,
            # Where a paper added to a tier board lands ( ◉ ) : a section id.
            # Unranked when nothing else is armed ; "" on a plain list.
            "section_target": target if sections else "" ,
        } ,
        "sections":   sections ,
        "columns":    columns ,
        "items":      items ,
        "staging":    staging ,
        "vocab":      { "tags": tags[ :400 ] } ,
    }


def item_count( doc ):
    """How many papers the board holds."""
    return len( ( doc or {} ).get( "items" ) or [] )


# ---------------------------------------------------------------------------
# Merge : a page's save over a board that moved underneath it
# ---------------------------------------------------------------------------
#
# The page posts the WHOLE document. When something else wrote in between -- an
# agent's ops , another tab -- that document is missing their change , and
# writing it as-is would quietly undo it. So the page says which version it
# started from ( base_rev ) and the server merges three ways : the BASE it
# started from , MINE ( what it posted ) and THEIRS ( what is stored now ).
#
# The rule everywhere is "mine if I changed it , theirs otherwise" , at the
# finest grain the document has :
#
#   where a row is   list / shelf / gone -- whichever side moved it wins , so a
#                    delete on either side beats an edit on the other
#   a row's fields   title , year , ... each on its own ; each CELL on its own
#   a row's tags     a set : theirs , less what I took off , plus what I put on
#   the list order   mine if I reordered the rows we share , theirs otherwise ;
#                    the rows only the other side has go in after the nearest
#                    row before them that survived
#   columns , tags   the same keyed merge , by column id / tag name
#   options          key by key

_ROW_SCALARS = ( "title" , "authors" , "doi" , "wid" , "pdf" , "year" , "journal" ,
    "placed" , "pending" , "added_at" )


def _pick( b , m , t ):
    return m if m != b else t


def _weave( primary , secondary , keep ):
    """`primary`'s order , restricted to `keep` , with whatever only `secondary`
    has slotted in after its nearest predecessor there."""
    out  = [ k for k in primary if k in keep ]
    have = set( out )
    for i , k in enumerate( secondary ):
        if k not in keep or k in have:
            continue
        at = 0
        for j in range( i - 1 , -1 , -1 ):
            if secondary[ j ] in have:
                at = out.index( secondary[ j ] ) + 1
                break
        out.insert( at , k )
        have.add( k )
    out.extend( sorted( k for k in keep if k not in have ) )
    return out


def _reordered( base , mine ):
    """Did MINE change the relative order of the keys it shares with BASE ?"""
    shared = set( base ) & set( mine )
    return [ k for k in mine if k in shared ] != [ k for k in base if k in shared ]


def _order( b , m , t , keep ):
    if _reordered( b , m ):
        return _weave( m , t , keep )
    return _weave( t , m , keep )


def _merge_keyed( b , m , t , key , entry ):
    """A keyed list ( columns , vocab tags ) : present unless a side that had it
    in BASE dropped it , each entry merged by `entry( b , m , t )` , in order."""
    bm = { key( x ): x for x in b }
    mm = { key( x ): x for x in m }
    tm = { key( x ): x for x in t }
    keep = set()
    for k in set( mm ) | set( tm ):
        if k in mm and k in tm:
            keep.add( k )
        elif k in mm and k not in bm:    # I added it
            keep.add( k )
        elif k in tm and k not in bm:    # they added it
            keep.add( k )
    order = _order( [ key( x ) for x in b ] , [ key( x ) for x in m ] ,
        [ key( x ) for x in t ] , keep )
    out = []
    for k in order:
        if k in mm and k in tm:
            out.append( entry( bm.get( k ) , mm[ k ] , tm[ k ] ) )
        else:
            out.append( mm.get( k ) or tm.get( k ) )
    return out


def _merge_dict( b , m , t ):
    b , m , t = b or {} , m or {} , t or {}
    return { k: _pick( b.get( k ) , m.get( k ) , t.get( k ) ) for k in list( t ) + [ k for k in m if k not in t ] }


def _merge_row( b , m , t ):
    """One paper both sides still have."""
    if b is None:
        # Both added it : mine where it says something , theirs otherwise.
        row = dict( t )
        for f in _ROW_SCALARS:
            if m.get( f ) not in ( None , "" , False ):
                row[ f ] = m[ f ]
        row[ "fields" ] = { k: ( m.get( "fields" , {} ).get( k ) or t.get( "fields" , {} ).get( k ) or "" )
            for k in set( m.get( "fields" ) or {} ) | set( t.get( "fields" ) or {} ) }
        row[ "tags" ] = list( { s.lower(): s for s in ( t.get( "tags" ) or [] ) + ( m.get( "tags" ) or [] ) }.values() )
        return row
    row = dict( t )
    for f in _ROW_SCALARS:
        row[ f ] = _pick( b.get( f ) , m.get( f ) , t.get( f ) )
    row[ "fields" ] = _merge_dict( b.get( "fields" ) , m.get( "fields" ) , t.get( "fields" ) )
    bt = { s.lower() for s in b.get( "tags" ) or [] }
    mt = { s.lower() for s in m.get( "tags" ) or [] }
    off  = bt - mt
    tags = [ s for s in ( t.get( "tags" ) or [] ) if s.lower() not in off ]
    have = { s.lower() for s in tags }
    for s in m.get( "tags" ) or []:
        if s.lower() not in bt and s.lower() not in have:
            tags.append( s )
            have.add( s.lower() )
    row[ "tags" ] = tags
    return row


def merge( base , mine , theirs ):
    """Three-way merge of whole board documents -- see the block comment above.
    All three are expected normalized ; the result is normalized."""
    base , mine , theirs = ( normalize( d ) for d in ( base , mine , theirs ) )

    def where( doc ):
        out = {}
        for loc in ( "items" , "staging" ):
            for r in doc.get( loc ) or []:
                out[ r[ "key" ] ] = ( loc , r )
        return out
    B , M , T = where( base ) , where( mine ) , where( theirs )
    result = {}
    for k in set( B ) | set( M ) | set( T ):
        bl = B[ k ][ 0 ] if k in B else None
        ml = M[ k ][ 0 ] if k in M else None
        tl = T[ k ][ 0 ] if k in T else None
        loc = ml if ml != bl else tl
        if loc is None:
            continue
        b , m , t = ( X[ k ][ 1 ] if k in X else None for X in ( B , M , T ) )
        row = _merge_row( b , m , t ) if ( m is not None and t is not None ) else ( m or t )
        result[ k ] = ( loc , row )

    lists = {}
    for loc in ( "items" , "staging" ):
        keep = { k for k , ( l , _ ) in result.items() if l == loc }
        seq  = lambda d: [ r[ "key" ] for r in d.get( loc ) or [] ]
        lists[ loc ] = [ result[ k ][ 1 ] for k in _order( seq( base ) , seq( mine ) , seq( theirs ) , keep ) ]

    columns = _merge_keyed( base[ "columns" ] , mine[ "columns" ] , theirs[ "columns" ] ,
        lambda c: c[ "id" ] ,
        lambda b , m , t: { "id": t[ "id" ] , "label": _pick( ( b or {} ).get( "label" ) , m[ "label" ] , t[ "label" ] ) } )
    tags = _merge_keyed( base[ "vocab" ][ "tags" ] , mine[ "vocab" ][ "tags" ] , theirs[ "vocab" ][ "tags" ] ,
        lambda v: v[ "name" ].lower() ,
        lambda b , m , t: { "name": _pick( ( b or {} ).get( "name" ) , m[ "name" ] , t[ "name" ] ) ,
                            "color": _pick( ( b or {} ).get( "color" ) , m.get( "color" ) , t.get( "color" ) ) } )
    return normalize( {
        "version":    VERSION ,
        "updated_at": theirs.get( "updated_at" ) ,
        "options":    _merge_dict( base[ "options" ] , mine[ "options" ] , theirs[ "options" ] ) ,
        "columns":    columns ,
        "items":      lists[ "items" ] ,
        "staging":    lists[ "staging" ] ,
        "vocab":      { "tags": tags } ,
    } )
