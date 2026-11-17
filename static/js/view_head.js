// A screen's heading and description fold away once the reader scrolls into
// its table, and come back at the top, so the rows get the room.
//
// The screen marks the part that folds with <header class="view-head">. From
// md up a table scrolls inside its own box (.data-table-scroll); on a phone
// the window scrolls. Either counts. It folds past a small way down and only
// unfolds back at the very top, so the page moving up as the header shrinks
// can never fold and unfold it in a loop.
const ViewHead = {
  // How far down, in pixels, before it folds; the window also has to clear
  // the header itself, which leaves the page as it folds.
  down: 48,
  top: 4,

  watch( view ) {
    const head = view.querySelector( ".view-head" );
    if ( !head ) return;
    const check = () => {
      if ( !view.classList.contains( "view-active" ) ) return;
      const tables = Array.from( view.querySelectorAll( ".data-table-scroll" ) ).map( ( box ) => box.scrollTop );
      const folded = view.classList.contains( "head-collapsed" );
      if ( !folded ) {
        const past = window.scrollY > this.down + head.offsetHeight || tables.some( ( top ) => top > this.down );
        if ( past ) this.fold( view , true );
      } else if ( window.scrollY <= this.top && tables.every( ( top ) => top <= this.top ) ) {
        this.fold( view , false );
      }
    };
    window.addEventListener( "scroll" , check , { passive: true } );
    // A table's own scroll does not bubble; catching it on the way down does.
    view.addEventListener( "scroll" , check , { passive: true , capture: true } );
    // Every visit to the screen starts unfolded (Nav scrolls it to the top).
    window.addEventListener( "hashchange" , () => this.fold( view , false ) );
  },

  fold( view , folded ) {
    // Only folded out of sight: #library-status is a live region, and still
    // speaks while folded.
    view.classList.toggle( "head-collapsed" , folded );
  },
};
