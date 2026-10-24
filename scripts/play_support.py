"""Engine-independent, strategy-preserving helpers for certificate play."""
from __future__ import annotations
import math
import shutil
import textwrap


class PositionHistory:
    """Append only to an unchanged mapped prefix; otherwise rebuild safely."""
    def __init__(self, factory, position=None):
        self.factory, self.position = factory, position
        self.moves = ()
        self._expected_hash = None if position is None else position.hash()
        self._valid = position is not None

    def invalidate(self):
        self._valid = False

    def sync(self, moves):
        current = tuple((int(side), int(cell)) for side, cell in moves)
        reuse = (self._valid and self.position is not None
                 and len(current) >= len(self.moves)
                 and current[:len(self.moves)] == self.moves
                 and self.position.hash() == self._expected_hash)
        start = len(self.moves) if reuse else 0
        self._valid = False
        if not reuse:
            self.position = self.factory()
        for side, cell in current[start:]:
            self.position.place(side, cell)
        self.moves = current
        self._expected_hash = self.position.hash()
        self._valid = True
        return self.position


def square_winner_after(n, board, cell):
    """O(n) axis-aligned check. Assumes no square existed before this move."""
    owner = board[cell]
    if owner not in (1, 2):
        return None
    row, col = divmod(cell, n)
    for gap in range(1, n):
        for rr in (row-gap, row+gap):
            if not 0 <= rr < n:
                continue
            for cc in (col-gap, col+gap):
                if (0 <= cc < n and board[row*n+cc] == owner
                        and board[rr*n+col] == owner and board[rr*n+cc] == owner):
                    return owner
    return None


class TerminalBoard:
    """Full board, aggregated overview, or labelled full-resolution viewport.

    An overview tile represents a region, never an individual cell. Actual
    move input always uses original zero-based coordinates, not tile indices.
    """
    MODES = ('auto', 'full', 'overview', 'center', 'last')

    def __init__(self, mode='auto', *, size=None):
        if mode not in self.MODES:
            raise ValueError('unknown board view')
        self.mode, self.focus, self.size = mode, None, size

    def set_view(self, request, n):
        parts = request.lower().split()
        if len(parts) == 1 and parts[0] in (*self.MODES, 'all'):
            self.mode = 'full' if parts[0] == 'all' else parts[0]
            self.focus = None
            return
        if len(parts) == 2:
            row, col = map(int, parts)
            if 0 <= row < n and 0 <= col < n:
                self.mode, self.focus = 'focus', (row, col)
                return
        raise ValueError('view auto|overview|center|last|full, or view ROW COL')

    def render(self, n, board, *, last=None, mark_cells=None):
        columns, lines = self.size or shutil.get_terminal_size(fallback=(80, 24))
        columns = max(12, columns)
        available = max(6, lines - 6)
        digits = len(str(n - 1))
        label, width = max(2, 2 * digits + 1), max(3, digits)
        max_cols = max(1, (columns - label - 2) // width)
        max_rows = max(1, available - 7)

        while True:
            mode = self.mode
            if mode == 'auto':
                mode = 'full' if n <= max_cols and n <= max_rows else 'overview'
            if mode == 'overview':
                result = self._overview(n, board, last, max_rows, max_cols, label, width)
            else:
                if mode == 'full':
                    r0 = c0 = 0
                    rows = cols = n
                else:
                    row, col = (divmod(last, n) if mode == 'last' and last is not None
                                else self.focus or (n // 2, n // 2))
                    rows, cols = min(n, max_rows), min(n, max_cols)
                    r0 = max(0, min(n - rows, row - rows // 2))
                    c0 = max(0, min(n - cols, col - cols // 2))
                marks = set(mark_cells or ())
                result = [f'Cells r={r0}..{r0+rows-1}, c={c0}..{c0+cols-1} of {n}x{n}',
                          ' ' * (label + 1) + ''.join(f'{c:^{width}}' for c in range(c0, c0+cols))]
                for row in range(r0, r0+rows):
                    tokens = []
                    for col in range(c0, c0+cols):
                        cell = row*n + col
                        char = '.XO'[board[cell]]
                        tok = f'[{char}]' if cell == last else f'*{char}' if cell in marks else char
                        tokens.append(f'{tok:^{width}}')
                    result.append(f'{row:>{label}}|' + ''.join(tokens))
                result.append('X=P1 O=P2 .=empty [ ]=last; coordinates start at 0.')
                if rows < n or cols < n:
                    hidden = [0, 0, 0]
                    for cell, owner in enumerate(board):
                        if owner and not (r0 <= cell//n < r0+rows and c0 <= cell%n < c0+cols):
                            hidden[owner] += 1
                    result.append(f'Hidden stones: X={hidden[1]} O={hidden[2]}; view overview shows all.')
            result.append('View: auto | overview | center | last | ROW COL | full')
            if columns < 60:
                # Brief captions leave room for actual cells on small screens.
                result[-1] = 'view ROW COL / help'
                if mode == 'overview':
                    rb, cb = math.ceil(n/max_rows), math.ceil(n/max_cols)
                    result[0] = f'{n}x{n} tiles {rb}x{cb}'
                    result[-3] = f'X={board.count(1)} O={board.count(2)} *=both'
                    result[-2] = 'r ranges; c starts'
                else:
                    result = [line.replace('X=P1 O=P2 .=empty [ ]=last; coordinates start at 0.',
                                           'X=P1 O=P2 [ ]=last')
                              .replace('; view overview shows all.', '') for line in result]
            if self.mode == 'full':
                return '\n'.join(result)
            wrapped = [part for line in result for part in
                       (textwrap.wrap(line, width=columns, replace_whitespace=False,
                                      drop_whitespace=False) or [''])]
            if len(wrapped) <= available or max_rows == 1:
                return '\n'.join(wrapped)
            max_rows -= 1

    @staticmethod
    def _overview(n,board,last,max_rows,max_cols,label,width):
        rb,cb=math.ceil(n/max_rows),math.ceil(n/max_cols)
        nr,nc=math.ceil(n/rb),math.ceil(n/cb)
        tiles=[[0]*nc for _ in range(nr)]; counts=[0,0,0]
        for cell,owner in enumerate(board):
            if owner:
                r,c=divmod(cell,n); tiles[r//rb][c//cb] |= owner; counts[owner]+=1
        latest=None if last is None else (last//n//rb,last%n//cb)
        out=[f'Overview {n}x{n}: each tile covers up to {rb} rows x {cb} cols.',
            ' '*(label+1)+''.join(f'{c*cb:^{width}}' for c in range(nc))]
        for r in range(nr):
            tokens=[]
            for c in range(nc):
                char='.XO*'[tiles[r][c]]
                tok=f'[{char}]' if (r,c) == latest else char
                tokens.append(f'{tok:^{width}}')
            name=str(r*rb) if rb == 1 else f'{r*rb}-{min(n-1,(r+1)*rb-1)}'
            out.append(f'{name:>{label}}|'+''.join(tokens))
        out.append(f'Tiles: X=P1 only O=P2 only *=both .=empty; X={counts[1]} O={counts[2]}')
        out.append('Row labels are ranges; column labels are tile start columns.')
        return out
