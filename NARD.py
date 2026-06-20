from __future__ import annotations

import copy
import math
import random
import time
import tkinter as tk
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple, Union

POINTS_COUNT = 24
CHECKERS_PER_PLAYER = 15
WHITE = "w"
BLACK = "b"

PATH_WHITE: Tuple[int, ...] = tuple(range(POINTS_COUNT))
PATH_BLACK: Tuple[int, ...] = tuple(range(12, POINTS_COUNT)) + tuple(range(12))

HOME_START_PATH_INDEX = 18

ANIM_MOVE_FRAMES = 60
ANIM_FPS_MS = 1000 // 60

TAG_SHELL = "shell"
TAG_PIECES = "pieces"
TAG_HINTS = "hints"
TAG_FLOATING = "floating"
TAG_CENTER_BAR = "center_bar"


@dataclass
class GameState:
    board: List[List[Any]]
    dice: List[int]
    current_turn: str
    first_turn: Dict[str, bool] = field(default_factory=lambda: {WHITE: True, BLACK: True})
    head_taken_this_turn: int = 0
    out_count: Dict[str, int] = field(default_factory=lambda: {WHITE: 0, BLACK: 0})
    is_double: bool = False

    def copy(self) -> "GameState":
        return GameState(
            board=copy.deepcopy(self.board),
            dice=self.dice[:],
            current_turn=self.current_turn,
            first_turn=dict(self.first_turn),
            head_taken_this_turn=self.head_taken_this_turn,
            out_count=dict(self.out_count),
            is_double=self.is_double,
        )


def initial_board() -> List[List[Any]]:
    b = [[0, None] for _ in range(POINTS_COUNT)]
    b[0] = [CHECKERS_PER_PLAYER, WHITE]
    b[12] = [CHECKERS_PER_PLAYER, BLACK]
    return b


def new_game_state() -> GameState:
    return GameState(
        board=initial_board(),
        dice=[],
        current_turn=WHITE,
        first_turn={WHITE: True, BLACK: True},
        head_taken_this_turn=0,
        out_count={WHITE: 0, BLACK: 0},
        is_double=False,
    )


def _path_for(color: str) -> Tuple[int, ...]:
    return PATH_WHITE if color == WHITE else PATH_BLACK


def _all_in_home(state: GameState, color: str) -> bool:
    path = _path_for(color)
    for i in range(POINTS_COUNT):
        cnt, col = state.board[i]
        if col == color and path.index(i) < HOME_START_PATH_INDEX:
            return False
    return True


def _farthest_from_home_path_index(state: GameState, color: str) -> int:
    """Минимальный индекс на пути среди шашек в доме (для правила выброса «с дальней»)."""
    path = _path_for(color)
    best: Optional[int] = None
    for i in range(POINTS_COUNT):
        cnt, col = state.board[i]
        if col != color or cnt <= 0:
            continue
        idx = path.index(i)
        if idx < HOME_START_PATH_INDEX:
            continue
        if best is None or idx < best:
            best = idx
    return -1 if best is None else best


def _dice_subsets(dice: List[int]) -> List[Tuple[int, List[int]]]:
    """
    Варианты хода одной шашкой: одна кость или сумма двух разных костей.
    Дубль: 1..min(4, len(dice)) одинаковых значений.
    Возвращает (сумма шагов, список значений костей для списания).
    """
    if not dice:
        return []
    n = len(dice)
    out: List[Tuple[int, List[int]]] = []
    seen: set = set()

    def add(cost: int, used: List[int]) -> None:
        key = (cost, tuple(sorted(used)))
        if key not in seen:
            seen.add(key)
            out.append((cost, used))

    if len(set(dice)) == 1:
        v = dice[0]
        for k in range(1, min(4, n) + 1):
            add(k * v, [v] * k)
        return out

    for i in range(n):
        add(dice[i], [dice[i]])
    for i in range(n):
        for j in range(i + 1, n):
            if dice[i] != dice[j]:
                add(dice[i] + dice[j], [dice[i], dice[j]])
    return out


def _can_take_from_head(state: GameState, color: str) -> bool:
    """С головы за ход — не более одной шашки, кроме первого хода при дубле (две)."""
    if state.head_taken_this_turn == 0:
        return True
    if state.first_turn[color] and state.is_double and state.head_taken_this_turn < 2:
        return True
    return False


def legal_moves_from_point(state: GameState, start: int) -> Dict[Union[int, str], List[int]]:
    """
    Все геометрически допустимые ходы с точки start с учётом головы и дома.
    Ключ: индекс точки или 'out'; значение: список значений костей (как в state.dice).
    """
    moves: Dict[Union[int, str], List[int]] = {}
    cnt, color = state.board[start]
    if cnt <= 0 or color != state.current_turn:
        return moves

    path = _path_for(color)
    start_idx = path.index(start)

    if start_idx == 0 and not _can_take_from_head(state, color):
        return moves

    all_home = _all_in_home(state, color)
    farthest_idx = _farthest_from_home_path_index(state, color) if all_home else -1

    for cost, dice_used in _dice_subsets(state.dice):
        target_idx = start_idx + cost
        if target_idx >= POINTS_COUNT:
            if not all_home:
                continue
            dist_to_end = POINTS_COUNT - start_idx
            if cost == dist_to_end:
                key: Union[int, str] = "out"
                if key not in moves or len(dice_used) < len(moves[key]):
                    moves[key] = dice_used
            elif cost > dist_to_end and start_idx == farthest_idx:
                key = "out"
                if key not in moves or len(dice_used) < len(moves[key]):
                    moves[key] = dice_used
        else:
            target_physical = path[target_idx]
            t_cnt, t_col = state.board[target_physical]
            if t_col in (None, color):
                if target_physical not in moves or len(dice_used) < len(moves[target_physical]):
                    moves[target_physical] = dice_used
    return moves


def remove_dice_values(dice: List[int], used: List[int]) -> List[int]:
    """Снимает по одному вхождению каждого значения из used (мультимножество)."""
    pool = dice[:]
    for v in used:
        if v in pool:
            pool.remove(v)
    return pool


def apply_move(state: GameState, start: int, end: Union[int, str], dice_used: List[int]) -> GameState:
    """Возвращает новое состояние после хода (копия)."""
    s = state.copy()
    path = _path_for(s.current_turn)
    if path.index(start) == 0:
        s.head_taken_this_turn += 1

    s.board[start][0] -= 1
    if s.board[start][0] == 0:
        s.board[start][1] = None

    if end == "out":
        s.out_count[s.current_turn] += 1
    else:
        s.board[end][1] = s.current_turn
        s.board[end][0] += 1

    s.dice = remove_dice_values(s.dice, dice_used)
    return s


def max_dice_usable(state: GameState) -> int:
    """
    Максимальное число «костей» (элементов списка dice), которые можно сыграть
    за оставшуюся часть хода (рекурсия по всем легальным продолжениям).
    """
    if not state.dice:
        return 0
    color = state.current_turn
    best = 0
    for start in range(POINTS_COUNT):
        if state.board[start][1] != color:
            continue
        for target, used in legal_moves_from_point(state, start).items():
            gain = len(used)
            nxt = apply_move(state, start, target, used)
            total = gain + max_dice_usable(nxt)
            if total > best:
                best = total
    return best


def legal_moves_maximal_first(
    state: GameState, start: int
) -> Dict[Union[int, str], List[int]]:
    """Только те ходы с start, которые входят в хотя бы одно максимальное по костям продолжение."""
    baseline = max_dice_usable(state)
    if baseline == 0:
        return {}
    out: Dict[Union[int, str], List[int]] = {}
    for target, used in legal_moves_from_point(state, start).items():
        gain = len(used)
        nxt = apply_move(state, start, target, used)
        if gain + max_dice_usable(nxt) == baseline:
            out[target] = used
    return out


def player_has_any_legal_move(state: GameState) -> bool:
    color = state.current_turn
    for i in range(POINTS_COUNT):
        if state.board[i][1] == color and legal_moves_maximal_first(state, i):
            return True
    return False


def _sigmoid(x: float) -> float:
    if x >= 60.0:
        return 1.0
    if x <= -60.0:
        return 0.0
    return 1.0 / (1.0 + math.exp(-x))


def _pip_count(state: GameState, color: str) -> int:
    """Суммарная дистанция до выброса (pip count) для игрока."""
    path = _path_for(color)
    total = 0
    for i in range(POINTS_COUNT):
        cnt, col = state.board[i]
        if col != color or cnt <= 0:
            continue
        idx = path.index(i)
        dist = (POINTS_COUNT - 1) - idx
        total += cnt * dist
    return total


def _td_features(state: GameState, for_color: str) -> List[float]:
    """
    Признаки позиции в стиле TD‑Gammon (value‑function).
    Длина фиксированная: 55.
    """
    opp = BLACK if for_color == WHITE else WHITE
    x: List[float] = []

    x.append(1.0)
    x.append(state.out_count[for_color] / float(CHECKERS_PER_PLAYER))
    x.append(state.out_count[opp] / float(CHECKERS_PER_PLAYER))

    x.append(_pip_count(state, for_color) / 345.0)
    x.append(_pip_count(state, opp) / 345.0)

    for i in range(POINTS_COUNT):
        cnt, col = state.board[i]
        if cnt <= 0 or col is None:
            x.append(0.0)
            x.append(0.0)
        elif col == for_color:
            x.append(min(1.0, cnt / float(CHECKERS_PER_PLAYER)))
            x.append(0.0)
        else:
            x.append(0.0)
            x.append(min(1.0, cnt / float(CHECKERS_PER_PLAYER)))

    path = _path_for(for_color)
    opp_path = _path_for(opp)
    home_self = 0
    home_opp = 0
    for i in range(POINTS_COUNT):
        cnt, col = state.board[i]
        if cnt <= 0:
            continue
        if col == for_color and path.index(i) >= HOME_START_PATH_INDEX:
            home_self += cnt
        elif col == opp and opp_path.index(i) >= HOME_START_PATH_INDEX:
            home_opp += cnt
    x.append(home_self / float(CHECKERS_PER_PLAYER))
    x.append(home_opp / float(CHECKERS_PER_PLAYER))
    return x


class TDGammonAI:
    """
    TD‑Gammon‑подход: value‑функция V(s) (0..1) + выбор хода по максимальному V.
    Для уровней сложности меняем «ошибочность» (epsilon) и число коротких симуляций.
    """

    def __init__(self):
        self.w: List[float] = self._init_weights()

    def _init_weights(self) -> List[float]:
        w = [0.0] * 55
        w[1] = 4.0
        w[2] = -4.0
        w[3] = -2.2
        w[4] = 2.2
        base = 5
        for i in range(48):
            w[base + i] = 0.15 if (i % 2 == 0) else -0.15
        w[-2] = 1.2
        w[-1] = -1.2
        return w

    def value(self, state: GameState, for_color: str) -> float:
        if state.out_count[for_color] >= CHECKERS_PER_PLAYER:
            return 1.0
        opp = BLACK if for_color == WHITE else WHITE
        if state.out_count[opp] >= CHECKERS_PER_PLAYER:
            return 0.0
        x = _td_features(state, for_color)
        z = 0.0
        n = min(len(x), len(self.w))
        for i in range(n):
            z += x[i] * self.w[i]
        return _sigmoid(z)

    def _rollout_value(self, state: GameState, for_color: str, depth: int, epsilon: float) -> float:
        s = state.copy()
        for _ in range(depth):
            if s.out_count[for_color] >= CHECKERS_PER_PLAYER:
                return 1.0
            opp = BLACK if for_color == WHITE else WHITE
            if s.out_count[opp] >= CHECKERS_PER_PLAYER:
                return 0.0

            d = [random.randint(1, 6), random.randint(1, 6)]
            s.is_double = d[0] == d[1]
            s.dice = [d[0], d[1], d[0], d[1]] if s.is_double else d

            if player_has_any_legal_move(s):
                mv = self.choose_first_step(s, epsilon=epsilon, rollouts=0, rollout_depth=0)
                if mv is not None:
                    st, tg, used = mv
                    s = apply_move(s, st, tg, used)

            if (not s.dice) or (not player_has_any_legal_move(s)):
                s.first_turn[s.current_turn] = False
                s.current_turn = BLACK if s.current_turn == WHITE else WHITE
                s.head_taken_this_turn = 0

        return self.value(s, for_color)

    def choose_first_step(
        self,
        state: GameState,
        epsilon: float,
        rollouts: int,
        rollout_depth: int,
    ) -> Optional[Tuple[int, Union[int, str], List[int]]]:
        all_moves = enumerate_all_first_moves(state)
        if not all_moves:
            return None
        if epsilon > 0.0 and random.random() < epsilon:
            return random.choice(all_moves)

        me = state.current_turn

        def mv_value(m: Tuple[int, Union[int, str], List[int]]) -> float:
            st, tg, used = m
            nxt = apply_move(state, st, tg, used)
            v = self.value(nxt, me)
            if rollouts > 0 and rollout_depth > 0:
                acc = 0.0
                for _ in range(rollouts):
                    acc += self._rollout_value(nxt, me, rollout_depth, epsilon=epsilon * 0.5)
                v = 0.55 * v + 0.45 * (acc / float(rollouts))
            return v

        return max(all_moves, key=mv_value)


_TD_AI = TDGammonAI()


def enumerate_all_first_moves(state: GameState) -> List[Tuple[int, Union[int, str], List[int]]]:
    moves: List[Tuple[int, Union[int, str], List[int]]] = []
    for start in range(POINTS_COUNT):
        if state.board[start][1] != state.current_turn:
            continue
        for target, used in legal_moves_maximal_first(state, start).items():
            moves.append((start, target, used))
    return moves


def choose_bot_move(state: GameState, level: str) -> Optional[Tuple[int, Union[int, str], List[int]]]:
    """
    Выбор хода бота. Не трогает UI.
    level: 'easy' | 'medium' | 'hard'
    """
    if level == "easy":
        return _TD_AI.choose_first_step(state, epsilon=0.55, rollouts=0, rollout_depth=0)
    if level == "medium":
        return _TD_AI.choose_first_step(state, epsilon=0.20, rollouts=6, rollout_depth=4)
    return _TD_AI.choose_first_step(state, epsilon=0.06, rollouts=22, rollout_depth=6)


class LongNardMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("Длинные Нарды - Премиум издание")

        self.is_fullscreen = True
        self.root.attributes("-fullscreen", self.is_fullscreen)

        self.update_screen_dims()

        self.clr_wood = "#1c110a"
        self.clr_board = "#3e2716"
        self.clr_accent = "#d4af37"
        self.clr_white = "#f0ede6"
        self.clr_black = "#1a1a1a"
        self.clr_selected = "#00cc66"

        self.canvas = tk.Canvas(
            root,
            width=self.sw,
            height=self.sh,
            bg=self.clr_wood,
            highlightthickness=0,
        )
        self.canvas.pack(fill="both", expand=True)

        self.timer_id = None
        self.game_active = False
        self.state: Optional[GameState] = None
        self._shell_drawn = False

        self.show_menu()

    def update_screen_dims(self):
        self.sw = self.root.winfo_screenwidth()
        self.sh = self.root.winfo_screenheight()

        base = min(self.sw, self.sh) * 0.85
        self.board_h = base * 0.85
        self.board_w = base * 1.3

        self.margin_x = (self.sw - self.board_w) / 2
        self.margin_y = (self.sh - self.board_h) / 2 + 20

        self.point_w = int(self.board_w // 12)
        self.piece_r = max(8, self.point_w // 2 - 4)
        self.out_pad = max(60, int(self.point_w * 0.9))
        self.center_bar_w = min(14, max(10, int(self.point_w * 0.35) - 3))
        self.center_bar_right_trim = 5
        half = self.center_bar_w / 2
        self.center_bar_left_half = half
        self.center_bar_right_half = max(4.0, half - float(self.center_bar_right_trim))
        self.font_ui = ("Verdana", max(10, int(self.sh * 0.015)), "bold")
        self.font_title = ("Garamond", max(24, int(self.sh * 0.07)), "bold")

    def toggle_fullscreen(self, event=None):
        self.is_fullscreen = not self.is_fullscreen
        self.root.attributes("-fullscreen", self.is_fullscreen)
        self.root.after(100, self.rebuild_ui)

    def rebuild_ui(self):
        self.update_screen_dims()
        self._shell_drawn = False
        if self.game_active and self.state is not None:
            self.draw_board(full_redraw=True)
            self.update_score_display()
        else:
            self.show_menu()

    def reset_game_state(self):
        self.state = new_game_state()
        self.selected_point: Optional[int] = None
        self.valid_moves: Dict = {}
        self.is_animating = False
        self.start_game_time = time.time()
        self.waiting_for_dice = False
        self.game_active = True
        self._shell_drawn = False
        self._anim_pending: Optional[Tuple[int, Union[int, str], List[int]]] = None

    def get_coords(self, index):
        if 0 <= index <= 11:
            x = self.margin_x + index * self.point_w + self.point_w // 2
            y = self.margin_y + self.board_h
            return x, y, -1
        col = 23 - index
        x = self.margin_x + col * self.point_w + self.point_w // 2
        y = self.margin_y
        return x, y, 1

    def draw_bg_texture(self):
        self.canvas.delete("bg_tex")
        for _ in range(100):
            x1 = random.randint(0, self.sw)
            y1 = random.randint(0, self.sh)
            self.canvas.create_line(
                x1,
                y1,
                x1 + random.randint(10, 80),
                y1,
                fill="#120a05",
                width=1,
                tags="bg_tex",
            )

    def show_menu(self):
        self.game_active = False
        self.state = None
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
        self.canvas.delete("all")
        self.draw_bg_texture()

        self.canvas.create_text(
            self.sw // 2,
            self.sh * 0.2,
            text="ДЛИННЫЕ НАРДЫ",
            font=self.font_title,
            fill=self.clr_accent,
        )

        btn_frame = tk.Frame(self.canvas, bg=self.clr_wood)
        self.canvas.create_window(self.sw // 2, self.sh * 0.5, window=btn_frame)

        btn_style = {
            "font": self.font_ui,
            "width": 25,
            "pady": 10,
            "padx": 10,
            "bg": "#2a1a10",
            "fg": self.clr_accent,
            "activebackground": "#4a301e",
            "activeforeground": "#fff",
            "relief": "ridge",
            "bd": 3,
            "cursor": "hand2",
        }

        tk.Button(btn_frame, text="ИГРОК VS ИГРОК", command=lambda: self.start_game_init(None, WHITE), **btn_style).pack(pady=10)
        tk.Button(btn_frame, text="ИГРАТЬ С БОТОМ", command=self.show_bot_setup, **btn_style).pack(pady=10)
        tk.Button(btn_frame, text="ПРАВИЛА", command=self.show_rules, **btn_style).pack(pady=10)
        tk.Button(btn_frame, text="ВЫХОД", command=self.root.destroy, **btn_style).pack(pady=10)

    def show_bot_setup(self):
        win = tk.Toplevel(self.root)
        win.title("Настройка игры")
        win.geometry("500x350")
        win.configure(bg="#1a110a")
        win.transient(self.root)
        win.grab_set()

        self.bot_lvl_var = tk.StringVar(value="medium")
        self.color_var = tk.StringVar(value=WHITE)

        tk.Label(win, text="СЛОЖНОСТЬ БОТА:", font=self.font_ui, bg="#1a110a", fg=self.clr_accent).pack(pady=(20, 10))
        f1 = tk.Frame(win, bg="#1a110a")
        f1.pack()
        for t, v in [("Легкий", "easy"), ("Средний", "medium"), ("Сложный", "hard")]:
            tk.Radiobutton(
                f1, text=t, variable=self.bot_lvl_var, value=v, font=self.font_ui, bg="#1a110a", fg="white", selectcolor="#3e2716"
            ).pack(side="left", padx=10)

        tk.Label(win, text="ВАШ ЦВЕТ:", font=self.font_ui, bg="#1a110a", fg=self.clr_accent).pack(pady=(30, 10))
        f2 = tk.Frame(win, bg="#1a110a")
        f2.pack()
        tk.Radiobutton(
            f2, text="Белые (Первые)", variable=self.color_var, value=WHITE, font=self.font_ui, bg="#1a110a", fg="white", selectcolor="#3e2716"
        ).pack(side="left", padx=10)
        tk.Radiobutton(
            f2, text="Черные (Вторые)", variable=self.color_var, value=BLACK, font=self.font_ui, bg="#1a110a", fg="white", selectcolor="#3e2716"
        ).pack(side="left", padx=10)

        tk.Button(win, text="НАЧАТЬ", font=self.font_ui, bg="#d4af37", fg="black", padx=20, command=lambda: self.start_bot_game(win)).pack(pady=30)

    def start_bot_game(self, window):
        self.bot_level = self.bot_lvl_var.get()
        self.human_color = self.color_var.get()
        window.destroy()
        self.start_game_init(self.bot_level, self.human_color)

    def show_rules(self):
        win = tk.Toplevel(self.root)
        win.title("Правила Игры")
        win.geometry("900x750")
        win.minsize(500, 400)
        win.configure(bg="#1a110a")
        win.transient(self.root)
        win.grab_set()

        title = tk.Label(win, text="ПРАВИЛА ДЛИННЫХ НАРД", font=("Garamond", 20, "bold"), bg="#1a110a", fg=self.clr_accent)
        title.pack(pady=10)

        text_frame = tk.Frame(win, bg="#1a110a")
        text_frame.pack(fill="both", expand=True, padx=20, pady=10)

        text_widget = tk.Text(text_frame, wrap="word", font=("Verdana", 11), bg="#2a1a10", fg="white", padx=15, pady=15, relief="flat")
        scrollbar = tk.Scrollbar(text_frame, command=text_widget.yview)
        text_widget.configure(yscrollcommand=scrollbar.set)

        scrollbar.pack(side="right", fill="y")
        text_widget.pack(side="left", fill="both", expand=True)

        rules_text = (
            "📜 ПРАВИЛА ИГРЫ «ДЛИННЫЕ НАРДЫ»\n\n"
            "🎯 ЦЕЛЬ ИГРЫ:\n"
            "Вывести все 15 своих шашек с доски раньше соперника.\n\n"
            "🧩 НАЧАЛЬНАЯ РАССТАНОВКА:\n"
            "• У каждого игрока по 15 шашек.\n"
            "• Белые начинают игру и располагаются в лунке 0.\n"
            "• Черные располагаются в лунке 12.\n"
            "• Все шашки каждого игрока стоят в одной стартовой позиции («голове»).\n\n"
            "🎲 ХОД И КУБИКИ:\n"
            "• Игроки ходят по очереди.\n"
            "• В начале хода бросаются 2 кубика.\n"
            "• Числа на кубиках — это количество шагов, на которое можно передвинуть шашки.\n"
            "• Можно использовать каждое число отдельно или суммарно.\n"
            "• Если выпал дубль (например 3-3), игрок делает 4 хода этим числом.\n\n"
            "➡️ ДВИЖЕНИЕ ШАШЕК:\n"
            "• Все шашки движутся против часовой стрелки.\n"
            "• Белые: от 0 → 23.\n"
            "• Черные: от 12 → 23 → 0 → 11.\n"
            "• Шашки можно ставить только на:\n"
            "  – пустую лунку\n"
            "  – или лунку со своими шашками\n"
            "• Ставить на лунку, занятую соперником, запрещено.\n\n"
            "🚫 БЛОКИРОВКА:\n"
            "• Если все возможные ходы заблокированы, игрок пропускает ход.\n\n"
            "🏁 ПРАВИЛО «ГОЛОВЫ»:\n"
            "• «Голова» — стартовая лунка игрока.\n"
            "• За один ход можно снять только 1 шашку с головы.\n"
            "• Исключение: в самый первый ход при дубле (3-3, 4-4, 6-6)\n"
            "  разрешено снять 2 шашки.\n\n"
            "🏠 ДОМ И ВЫВОД ШАШЕК (BEAR-OFF):\n"
            "• Вывод возможен только когда все шашки игрока находятся в доме.\n"
            "• Дом белых: лунки 18–23.\n"
            "• Дом черных: лунки 6–11.\n"
            "• Шашка выводится при точном значении кубика.\n"
            "• Если число больше — можно вывести самую дальнюю шашку.\n\n"
            "⚙️ ОСОБЕННОСТИ ХОДА:\n"
            "• Нужно использовать максимально возможное количество ходов.\n"
            "• Если можно сделать оба хода — их нужно сделать.\n"
            "• Если возможен только один — выполняется он.\n\n"
            "🤖 РЕЖИМЫ ИГРЫ:\n"
            "• Игрок vs Игрок — игра вдвоем.\n"
            "• Игрок vs Бот:\n"
            "  – Легкий (TD‑Gammon): часто выбирает ход случайно и почти не просчитывает — легко ошибается.\n"
            "  – Средний (TD‑Gammon): обычно выбирает ход по оценке позиции, но иногда «рискует/ошибается», делает немного симуляций.\n"
            "  – Сложный (TD‑Gammon): почти всегда выбирает лучший по оценке ход, делает больше симуляций и редко ошибается.\n\n"
            "🏆 ПОБЕДА:\n"
            "• Побеждает игрок, который первым вывел все 15 шашек.\n"
            "• При выходе из игры текущий игрок считается проигравшим.\n\n"
            "💡 ПОДСКАЗКИ:\n"
            "• Выбирайте шашку кликом.\n"
            "• Доступные ходы подсвечиваются (используемые кости).\n"
        )
        text_widget.insert("1.0", rules_text)
        text_widget.config(state="disabled")

        tk.Button(win, text="ЗАКРЫТЬ", font=self.font_ui, bg="#3e2716", fg=self.clr_accent, padx=20, command=win.destroy).pack(pady=15)

    def start_game_init(self, bot_level, human_color):
        self.canvas.delete("all")
        self.draw_bg_texture()
        self.bot_level = bot_level
        self.human_color = human_color

        self.reset_game_state()
        self.canvas.bind("<Button-1>", self.on_click)

        self.timer_text_id = self.canvas.create_text(
            self.sw // 2,
            self.sh * 0.03,
            text="00:00",
            fill=self.clr_accent,
            font=("Consolas", int(self.sh * 0.025), "bold"),
            tags="ui",
        )
        self.score_text_id = self.canvas.create_text(self.sw // 2, self.sh * 0.07, text="", fill="white", font=self.font_ui, tags="ui")

        mode_str = f"БОТ: {self.bot_level.upper()}" if self.bot_level else "PVP"
        self.canvas.create_text(self.sw // 2, self.sh * 0.11, text=mode_str, fill=self.clr_accent, font=self.font_ui, tags="ui")

        btn_quit = tk.Button(self.root, text="ВЫХОД", font=("Arial", 9, "bold"), bg="#5e1914", fg="white", command=self.confirm_exit)
        self.canvas.create_window(self.sw - 100, 50, window=btn_quit, tags="ui")

        self.update_timer()
        self.draw_board(full_redraw=True)
        self.root.after(800, self.animate_dice)

    def update_timer(self):
        if self.game_active:
            elapsed = int(time.time() - self.start_game_time)
            self.canvas.itemconfig(self.timer_text_id, text=f"{elapsed//60:02d}:{elapsed%60:02d}")
            self.timer_id = self.root.after(1000, self.update_timer)

    def update_score_display(self):
        if hasattr(self, "score_text_id") and self.score_text_id and self.state:
            info = f"ВЫБРОШЕНО: Белые {self.state.out_count[WHITE]} | Черные {self.state.out_count[BLACK]}"
            info += f"   |   ХОД: {'БЕЛЫХ' if self.state.current_turn == WHITE else 'ЧЕРНЫХ'}"
            self.canvas.itemconfig(self.score_text_id, text=info)

    def draw_piece(self, x, y, color, is_selected=False, tags="pieces"):
        main_col = self.clr_white if color == WHITE else self.clr_black
        highlight = self.clr_selected if is_selected else ("#999" if color == WHITE else "#444")
        r = self.piece_r

        self.canvas.create_oval(x - r, y - r, x + r, y + r, fill=main_col, outline=highlight, width=2, tags=tags)
        if color == WHITE:
            self.canvas.create_oval(x - r * 0.6, y - r * 0.8, x + r * 0.2, y - r * 0.2, fill="#fff", outline="", tags=tags)
        else:
            self.canvas.create_oval(x - r * 0.6, y - r * 0.8, x + r * 0.2, y - r * 0.2, fill="#555", outline="", tags=tags)

    def _draw_board_shell(self):
        """Рамка, треугольники, зона выброса, кубики — редко меняются."""
        self.canvas.delete(TAG_SHELL)
        self.canvas.create_rectangle(
            self.margin_x - 20,
            self.margin_y - 20,
            self.margin_x + self.board_w + 20,
            self.margin_y + self.board_h + 20,
            fill=self.clr_wood,
            outline="#0a0502",
            width=10,
            tags=TAG_SHELL,
        )
        self.canvas.create_rectangle(
            self.margin_x, self.margin_y, self.margin_x + self.board_w, self.margin_y + self.board_h, fill=self.clr_board, tags=TAG_SHELL
        )

        for i in range(POINTS_COUNT):
            cx, cy, direction = self.get_coords(i)
            color = "#5c4033" if i % 2 == 0 else "#2a1a10"
            x_l, x_r = cx - self.point_w // 2, cx + self.point_w // 2
            h_tri = self.board_h * 0.42
            pts = [x_l, cy, x_r, cy, cx, cy - h_tri] if direction == -1 else [x_l, cy, x_r, cy, cx, cy + h_tri]
            self.canvas.create_polygon(pts, fill=color, outline="#1a110a", tags=TAG_SHELL)

        mid_x = self.margin_x + self.board_w // 2
        bar_l_half = getattr(self, "center_bar_left_half", self.center_bar_w / 2)
        bar_r_half = getattr(self, "center_bar_right_half", self.center_bar_w / 2)
        self.canvas.create_rectangle(
            mid_x - bar_l_half,
            self.margin_y,
            mid_x + bar_r_half,
            self.margin_y + self.board_h,
            fill=self.clr_wood,
            outline="black",
            tags=(TAG_SHELL, TAG_CENTER_BAR),
        )

        white_out_x, white_out_y = self.margin_x - self.out_pad, self.margin_y + 20
        self.canvas.create_rectangle(
            white_out_x,
            white_out_y,
            white_out_x + 40,
            white_out_y + self.board_h * 0.4,
            fill="#1a110a",
            outline=self.clr_accent,
            width=3,
            tags=TAG_SHELL,
        )
        self.canvas.create_text(
            white_out_x + 20, white_out_y - 15, text="ВЫХОД БЕЛЫЕ", fill=self.clr_accent, font=("Arial", 8), tags=TAG_SHELL
        )

        black_out_x, black_out_y = (
            self.margin_x + self.board_w + (self.out_pad - 40),
            self.margin_y + self.board_h - 20 - self.board_h * 0.4,
        )
        self.canvas.create_rectangle(
            black_out_x,
            black_out_y,
            black_out_x + 40,
            black_out_y + self.board_h * 0.4,
            fill="#1a110a",
            outline=self.clr_accent,
            width=3,
            tags=TAG_SHELL,
        )
        self.canvas.create_text(
            black_out_x + 20,
            black_out_y + self.board_h * 0.4 + 15,
            text="ВЫХОД ЧЕРНЫЕ",
            fill=self.clr_accent,
            font=("Arial", 8),
            tags=TAG_SHELL,
        )

    def _draw_dice_on_shell(self, dice_vals: Optional[List[int]]):
        """Обновляет только прямоугольники кубиков на слое shell."""
        self.canvas.delete("dice_draw")
        if not dice_vals:
            return
        mid_x = self.margin_x + self.board_w // 2
        for idx, v in enumerate(dice_vals):
            d_size = self.sh * 0.05
            n = len(dice_vals)
            half_left = getattr(self, "center_bar_left_half", self.center_bar_w / 2)
            half_right = getattr(self, "center_bar_right_half", self.center_bar_w / 2)
            edge_gap = 5.0
            first_center_offset_left = half_left + edge_gap + (d_size / 2)
            first_center_offset_right = half_right + edge_gap + (d_size / 2)
            step = d_size + 12

            if n == 1:
                centers = [mid_x]
            elif n == 2:
                centers = [mid_x - first_center_offset_left, mid_x + first_center_offset_right]
            elif n == 3:
                centers = [
                    mid_x - (first_center_offset_left + step),
                    mid_x - first_center_offset_left,
                    mid_x + first_center_offset_right,
                ]
            else:
                centers = [
                    mid_x - (first_center_offset_left + step),
                    mid_x - first_center_offset_left,
                    mid_x + first_center_offset_right,
                    mid_x + (first_center_offset_right + step),
                ]
                if n > 4:
                    extra = n - 4
                    for k in range(extra):
                        dist = (first_center_offset_left if k % 2 == 0 else first_center_offset_right) + (2 + k // 2) * step
                        centers.append(mid_x - dist if k % 2 == 0 else mid_x + dist)

            x_center = centers[idx]
            dx = x_center - (d_size / 2)
            dy = self.margin_y + self.board_h / 2
            self.canvas.create_rectangle(
                dx,
                dy - d_size / 2,
                dx + d_size,
                dy + d_size / 2,
                fill="#f4e7d3",
                outline="#4a301e",
                width=2,
                tags=(TAG_SHELL, "dice_draw"),
            )
            self.canvas.create_text(
                dx + d_size / 2,
                dy,
                text=str(v),
                font=("Arial", int(d_size * 0.6), "bold"),
                fill="#000",
                tags=(TAG_SHELL, "dice_draw"),
            )

    def draw_out_checkers(self, cx, start_y, count, color, direction, tags=TAG_PIECES):
        step = min(12, (self.board_h * 0.4 - 20) / max(15, 1))
        for i in range(count):
            y = start_y + (i * step) * direction
            main_col = self.clr_white if color == WHITE else self.clr_black
            self.canvas.create_oval(cx - 10, y - 10, cx + 10, y + 10, fill=main_col, outline="#555", tags=tags)

    def _triangle_height(self):
        return self.board_h * 0.42

    def _stack_step(self, count: int) -> float:
        """Шаг укладки шашек как было раньше (сжатие по высоте треугольника)."""
        h_tri = self._triangle_height()
        return min(self.piece_r * 2.2, h_tri / max(count, 1))

    def _stack_top_xy(self, point_index: int, count: int) -> Tuple[float, float]:
        """
        Экранные координаты верхней шашки в стопке.
        ВАЖНО: используем тот же шаг, что и в фактической отрисовке (`_stack_step`),
        иначе при больших стопках возникает «подвисание/рывок» при пересчёте.
        """
        cx, cy, direction = self.get_coords(point_index)
        if count <= 0:
            return float(cx), float(cy)
        step = self._stack_step(count)
        y = cy + (self.piece_r + 5 + (count - 1) * step) * direction
        return float(cx), float(y)

    def _catmull_rom_polyline(self, pts: List[Tuple[float, float]], samples_per_seg: int = 18) -> List[Tuple[float, float]]:
        """
        Сглаживает путь через контрольные точки (Catmull–Rom) в полилинию.
        Это убирает резкие «углы» на стыках и делает пересечение центра ровным.
        """
        if not pts or len(pts) < 2:
            return pts[:]
        if samples_per_seg < 4:
            samples_per_seg = 4

        out: List[Tuple[float, float]] = []
        n = len(pts)

        def p(i: int) -> Tuple[float, float]:
            if i < 0:
                return pts[0]
            if i >= n:
                return pts[-1]
            return pts[i]

        for i in range(n - 1):
            p0 = p(i - 1)
            p1 = p(i)
            p2 = p(i + 1)
            p3 = p(i + 2)
            for s in range(samples_per_seg):
                t = s / samples_per_seg
                t2 = t * t
                t3 = t2 * t
                x = 0.5 * (
                    (2 * p1[0])
                    + (-p0[0] + p2[0]) * t
                    + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2
                    + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                )
                y = 0.5 * (
                    (2 * p1[1])
                    + (-p0[1] + p2[1]) * t
                    + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2
                    + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                )
                if not out:
                    out.append((x, y))
                else:
                    lx, ly = out[-1]
                    if (x - lx) * (x - lx) + (y - ly) * (y - ly) > 1e-6:
                        out.append((x, y))
        out.append(pts[-1])
        return out

    def _quadratic_bezier_polyline(
        self,
        p0: Tuple[float, float],
        p1: Tuple[float, float],
        p2: Tuple[float, float],
        samples: int = 60,
    ) -> List[Tuple[float, float]]:
        """Квадратичная Bezier-кривая в полилинию (без углов/перелётов)."""
        if samples < 8:
            samples = 8
        out: List[Tuple[float, float]] = []
        for i in range(samples + 1):
            t = i / samples
            u = 1.0 - t
            x = (u * u) * p0[0] + 2 * u * t * p1[0] + (t * t) * p2[0]
            y = (u * u) * p0[1] + 2 * u * t * p1[1] + (t * t) * p2[1]
            if not out:
                out.append((x, y))
            else:
                lx, ly = out[-1]
                if (x - lx) * (x - lx) + (y - ly) * (y - ly) > 1e-6:
                    out.append((x, y))
        return out

    def _draw_pieces_layer(
        self,
        temp_dice: Optional[List[int]] = None,
        hide_source_top: Optional[int] = None,
    ) -> None:
        """Только фишки на доске, выброшенные и кубики (без подсказок)."""
        self.canvas.delete(TAG_PIECES)
        assert self.state is not None
        board = self.state.board
        h_tri = self._triangle_height()

        for i in range(POINTS_COUNT):
            cx, cy, direction = self.get_coords(i)
            cnt, pcol = board[i]
            if cnt > 0:
                step = self._stack_step(cnt)
                for j in range(cnt):
                    if hide_source_top is not None and i == hide_source_top and j == cnt - 1:
                        continue
                    py = cy + (self.piece_r + 5 + j * step) * direction
                    sel = self.selected_point == i and j == cnt - 1
                    self.draw_piece(cx, py, pcol, is_selected=sel, tags=TAG_PIECES)

        white_out_x, white_out_y = self.margin_x - self.out_pad, self.margin_y + 20
        black_out_x, black_out_y = (
            self.margin_x + self.board_w + (self.out_pad - 40),
            self.margin_y + self.board_h - 20 - self.board_h * 0.4,
        )
        self.draw_out_checkers(white_out_x + 20, white_out_y + 10, self.state.out_count[WHITE], WHITE, 1)
        self.draw_out_checkers(black_out_x + 20, black_out_y + self.board_h * 0.4 - 10, self.state.out_count[BLACK], BLACK, -1)

        cur_dice = temp_dice if temp_dice is not None else self.state.dice
        self._draw_dice_on_shell(cur_dice)

    def _draw_hints_layer(self) -> None:
        """Подсказки только при выбранной шашке; перед отрисовкой старые подсказки снимаются."""
        self.canvas.delete(TAG_HINTS)
        if (
            not self.state
            or self.is_animating
            or self.selected_point is None
            or not self.valid_moves
        ):
            return

        board = self.state.board
        turn = self.state.current_turn
        white_out_x, white_out_y = self.margin_x - self.out_pad, self.margin_y + 20
        black_out_x, black_out_y = (
            self.margin_x + self.board_w + (self.out_pad - 40),
            self.margin_y + self.board_h - 20 - self.board_h * 0.4,
        )

        for target, dice_used in self.valid_moves.items():
            du = dice_used if isinstance(dice_used, list) else [dice_used]
            hint_sum = sum(du)
            label = "-".join(str(x) for x in du) if len(du) > 1 else str(hint_sum)
            if target == "out":
                tx, ty = (
                    (white_out_x + 20, white_out_y - 20)
                    if turn == WHITE
                    else (black_out_x + 20, black_out_y + self.board_h * 0.4 + 20)
                )
                self._draw_move_hint(tx, ty, label, 1)
            else:
                tx, ty, td = self.get_coords(target)
                t_cnt, t_col = board[target]
                t_py = (
                    ty + (self.piece_r + 5 + t_cnt * (self.piece_r * 2.2)) * td
                    if t_col == turn
                    else ty + (self.piece_r + 5) * td
                )
                self._draw_move_hint(tx, t_py, label, td)

    def draw_board(self, full_redraw: bool = False, temp_dice: Optional[List[int]] = None):
        if not self.state:
            return
        if full_redraw or not self._shell_drawn:
            self._draw_board_shell()
            self._shell_drawn = True
        self.update_score_display()
        if not self.is_animating:
            self.canvas.delete(TAG_FLOATING)
        self._draw_pieces_layer(temp_dice=temp_dice, hide_source_top=None)
        self._draw_hints_layer()
        self._apply_z_order()

    def _apply_z_order(self) -> None:
        """
        Порядок слоёв (снизу вверх):
        - фон/корпус (shell)
        - шашки (pieces) и летящая (floating)
        - центральная перегородка (center_bar)
        - кубики (dice_draw), подсказки (hints), UI — всегда поверх всего
        """
        self.canvas.tag_raise(TAG_PIECES)
        self.canvas.tag_raise(TAG_FLOATING)
        self.canvas.tag_raise(TAG_CENTER_BAR)
        self.canvas.tag_raise("dice_draw")
        self.canvas.tag_raise(TAG_HINTS)
        self.canvas.tag_raise("ui")

    def _draw_move_hint(self, cx, piece_y, label: str, direction):
        rw, rh = 32, 24
        tri_h = 18
        offset = (tri_h + rh) * (-direction)
        rect_y = piece_y - offset
        self.canvas.create_rectangle(
            cx - rw // 2,
            rect_y - rh // 2,
            cx + rw // 2,
            rect_y + rh // 2,
            fill="#7bed9f",
            outline="white",
            width=2,
            tags=TAG_HINTS,
        )
        self.canvas.create_text(cx, rect_y, text=label, fill="black", font=("Arial", 11, "bold"), tags=TAG_HINTS)
        base_y = rect_y + (rh // 2) * (-direction)
        apex_y = piece_y
        self.canvas.create_polygon(cx, apex_y, cx - 12, base_y, cx + 12, base_y, fill="#7bed9f", outline="white", width=2, tags=TAG_HINTS)

    def calc_moves(self, start: int) -> Dict:
        if not self.state:
            return {}
        return legal_moves_maximal_first(self.state, start)

    def _move_endpoints(self, start: int, end: Union[int, str]) -> Tuple[float, float, float, float, str]:
        """Экранные координаты верхней шашки на start и целевой точки (до изменения state)."""
        assert self.state is not None
        color = self.state.current_turn
        cnt = self.state.board[start][0]
        sx, sy = self._stack_top_xy(start, cnt)

        if end == "out":
            if color == WHITE:
                ex, ey = (self.margin_x - self.out_pad + 20), self.margin_y + 40
            else:
                ex, ey = (self.margin_x + self.board_w + (self.out_pad - 20)), self.margin_y + self.board_h - 40
        else:
            ex, ey, ed = self.get_coords(end)
            cnt_end = self.state.board[end][0]
            if self.state.board[end][1] == color:
                step_new = self._stack_step(cnt_end + 1)
                ey = ey + (self.piece_r + 5 + cnt_end * step_new) * ed
            else:
                ey = ey + (self.piece_r + 5) * ed
        return sx, sy, float(ex), float(ey), color

    def animate_move(self, start: int, end: Union[int, str], dice_used: List[int]) -> None:
        """
        Плавный линейный перенос шашки: верхняя с start скрыта в слое pieces,
        движущаяся отрисовывается только с тегом floating; каждый кадр обновляется только floating.
        """
        self.is_animating = True
        du = dice_used if isinstance(dice_used, list) else [dice_used]

        self.selected_point = None
        self.valid_moves = {}
        self.canvas.delete(TAG_HINTS)

        sx, sy, ex, ey, col = self._move_endpoints(start, end)
        self._anim_pending = (start, end, du)
        self._anim_sx, self._anim_sy = sx, sy
        self._anim_ex, self._anim_ey = ex, ey
        self._anim_color = col
        self._anim_frame = 0
        self._anim_frames = ANIM_MOVE_FRAMES

        center_y = self.margin_y + self.board_h / 2
        self._anim_arc_dir = -1 if sy > center_y else 1
        path = _path_for(col)
        self._anim_from_head = path.index(start) == 0

        mid_x = self.margin_x + self.board_w / 2
        half_left = getattr(self, "center_bar_left_half", self.center_bar_w / 2)
        half_right = getattr(self, "center_bar_right_half", self.center_bar_w / 2)
        bar_half = max(half_left, half_right) + (self.piece_r + 6)
        bar_l, bar_r = mid_x - bar_half, mid_x + bar_half
        pad = self.piece_r * 1.8

        pts: List[Tuple[float, float]] = [(sx, sy)]
        self._anim_detour_side: Optional[int] = None
        if end != "out":
            crosses_bar = (sx < bar_l and ex > bar_r) or (sx > bar_r and ex < bar_l)
            if crosses_bar:
                side_x = (bar_l - pad) if sx < bar_l else (bar_r + pad)
                self._anim_detour_side = -1 if sx < bar_l else 1
                p0 = (sx, sy)
                p1 = (side_x, center_y)
                p2 = (ex, ey)
                self._anim_pts = [p0, p1, p2]
                self._anim_poly = self._quadratic_bezier_polyline(p0, p1, p2, samples=max(40, self._anim_frames))
                self.canvas.delete(TAG_FLOATING)
                self._draw_pieces_layer(temp_dice=None, hide_source_top=start)
                self._anim_step_linear()
                return
        pts.append((ex, ey))
        self._anim_pts = pts
        self._anim_poly = self._catmull_rom_polyline(pts, samples_per_seg=20)

        self.canvas.delete(TAG_FLOATING)
        self._draw_pieces_layer(temp_dice=None, hide_source_top=start)
        self._anim_step_linear()

    def _anim_step_linear(self) -> None:
        total = self._anim_frames
        f = self._anim_frame
        if f > total:
            self.canvas.delete(TAG_FLOATING)
            pending = self._anim_pending
            self._anim_pending = None
            if pending is not None:
                s, e, d = pending
                self.complete_move(s, e, d)
            return

        if f >= total:
            x, y = self._anim_ex, self._anim_ey
            self.canvas.delete(TAG_FLOATING)
            self.draw_piece(x, y, self._anim_color, is_selected=False, tags=TAG_FLOATING)
            self._anim_frame = total + 1
            self.root.after(0, self._anim_step_linear)
            return

        t = (f / total) if total else 1.0
        t = max(0.0, min(1.0, t))

        te = t * t * (3 - 2 * t)

        pts = getattr(self, "_anim_poly", None)
        if not pts or len(pts) < 2:
            pts = [(self._anim_sx, self._anim_sy), (self._anim_ex, self._anim_ey)]

        seg_lengths: List[float] = []
        total_len = 0.0
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            ln = ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
            seg_lengths.append(ln)
            total_len += ln
        if total_len <= 1e-6:
            x, y = pts[-1]
            seg_i = 0
            segs = 1
        else:
            dist = te * total_len
            acc = 0.0
            seg_i = 0
            for i, ln in enumerate(seg_lengths):
                if dist <= acc + ln or i == len(seg_lengths) - 1:
                    seg_i = i
                    break
                acc += ln
            ln = seg_lengths[seg_i]
            local = 0.0 if ln <= 1e-6 else (dist - acc) / ln
            x0, y0 = pts[seg_i]
            x1, y1 = pts[seg_i + 1]
            x = x0 + (x1 - x0) * local
            y = y0 + (y1 - y0) * local
            segs = len(seg_lengths)

        lift = math.sin(math.pi * t)
        base = 0.025 if getattr(self, "_anim_from_head", False) else 0.045
        arc_h = self.sh * base
        arc_scale = 0.0 if getattr(self, "_anim_detour_side", None) is not None else 1.0
        y += getattr(self, "_anim_arc_dir", 1) * arc_h * lift * arc_scale
        self.canvas.delete(TAG_FLOATING)
        self.draw_piece(x, y, self._anim_color, is_selected=False, tags=TAG_FLOATING)
        self._apply_z_order()
        self._anim_frame += 1
        self.root.after(ANIM_FPS_MS, self._anim_step_linear)

    def complete_move(self, start, end, dice_used):
        dice_used = dice_used if isinstance(dice_used, list) else [dice_used]
        assert self.state is not None

        self.state = apply_move(self.state, start, end, dice_used)

        self.selected_point = None
        self.is_animating = False

        if self.state.out_count[self.state.current_turn] == CHECKERS_PER_PLAYER:
            self.show_victory_screen(self.state.current_turn)
            return

        has_moves = player_has_any_legal_move(self.state)

        if not self.state.dice or not has_moves:
            self.next_turn()
        else:
            self.draw_board(full_redraw=False)
            self.trigger_bot_if_needed()

    def next_turn(self):
        assert self.state is not None
        self.state.first_turn[self.state.current_turn] = False
        self.state.current_turn = BLACK if self.state.current_turn == WHITE else WHITE
        self.state.head_taken_this_turn = 0
        self.selected_point = None
        self.valid_moves = {}
        self.draw_board(full_redraw=False)
        self.root.after(500, self.animate_dice)

    def animate_dice(self):
        self.waiting_for_dice = True
        for i in range(10):
            self.root.after(i * 50, lambda s=i: self._dice_roll_step(s))

    def _dice_roll_step(self, step):
        if not self.game_active or self.state is None:
            return
        d = [random.randint(1, 6), random.randint(1, 6)]
        self.draw_board(full_redraw=False, temp_dice=d)
        if step == 9:
            self.state.is_double = d[0] == d[1]
            self.state.dice = [d[0], d[1], d[0], d[1]] if self.state.is_double else d
            self.waiting_for_dice = False
            self.draw_board(full_redraw=False)

            if not player_has_any_legal_move(self.state):
                self.root.after(1000, self.next_turn)
            else:
                self.trigger_bot_if_needed()

    def trigger_bot_if_needed(self):
        if self.bot_level and self.state and self.state.current_turn != self.human_color:
            self.root.after(500, self.bot_turn_step)

    def bot_turn_step(self):
        if not self.game_active or self.is_animating or self.waiting_for_dice or not self.state or not self.state.dice:
            return
        move = choose_bot_move(self.state, self.bot_level)
        if move is None:
            self.next_turn()
            return
        start, target, dice_used = move
        self.animate_move(start, target, dice_used)

    def on_click(self, event):
        if (
            self.is_animating
            or self.waiting_for_dice
            or not self.game_active
            or not self.state
            or (self.bot_level and self.state.current_turn != self.human_color)
        ):
            return

        white_out_x, black_out_x = self.margin_x - self.out_pad, self.margin_x + self.board_w + (self.out_pad - 40)

        if self.selected_point is not None and "out" in self.valid_moves:
            if self.state.current_turn == WHITE and white_out_x <= event.x <= white_out_x + 60 and self.margin_y <= event.y <= self.margin_y + self.board_h:
                self.animate_move(self.selected_point, "out", self.valid_moves["out"])
                return
            elif self.state.current_turn == BLACK and black_out_x <= event.x <= black_out_x + 60 and self.margin_y <= event.y <= self.margin_y + self.board_h:
                self.animate_move(self.selected_point, "out", self.valid_moves["out"])
                return

        for i in range(POINTS_COUNT):
            cx, cy, direction = self.get_coords(i)
            if cx - self.point_w // 2 <= event.x <= cx + self.point_w // 2:
                if (direction == -1 and event.y > self.margin_y + self.board_h / 2) or (
                    direction == 1 and event.y < self.margin_y + self.board_h / 2
                ):
                    if self.selected_point is not None and i in self.valid_moves:
                        self.animate_move(self.selected_point, i, self.valid_moves[i])
                        return
                    elif self.state.board[i][1] == self.state.current_turn:
                        self.selected_point = i
                        self.valid_moves = self.calc_moves(i)
                        self.draw_board(full_redraw=False)
                        return

        self.selected_point = None
        self.valid_moves = {}
        self.draw_board(full_redraw=False)

    def confirm_exit(self):
        if not self.game_active:
            self.show_menu()
            return
        win = tk.Toplevel(self.root)
        win.title("Выход из игры")
        win.geometry("400x180")
        win.configure(bg="#1a110a")
        win.transient(self.root)
        win.grab_set()
        tk.Label(win, text="Сдаться и выйти в меню?", font=self.font_ui, bg="#1a110a", fg="white").pack(pady=(25, 15))
        tk.Label(win, text="Противник будет объявлен победителем.", font=("Verdana", 10), bg="#1a110a", fg="#aaa").pack(pady=5)
        f = tk.Frame(win, bg="#1a110a")
        f.pack(pady=20)

        def do_surrender():
            win.destroy()
            surrendering = self.human_color if self.bot_level else self.state.current_turn if self.state else WHITE
            winner = BLACK if surrendering == WHITE else WHITE
            self.show_victory_screen(winner, surrendered=True)

        tk.Button(f, text="Да, сдаться", font=self.font_ui, bg="#5e1914", fg="white", command=do_surrender).pack(side="left", padx=10)
        tk.Button(f, text="Отмена", font=self.font_ui, bg="#3e2716", fg=self.clr_accent, command=win.destroy).pack(side="left", padx=10)

    def show_victory_screen(self, winner, surrendered=False):
        self.game_active = False
        if self.timer_id:
            self.root.after_cancel(self.timer_id)
        elapsed = int(time.time() - self.start_game_time)
        mins, secs = elapsed // 60, elapsed % 60
        win_text = "БЕЛЫЕ ПОБЕДИЛИ!" if winner == WHITE else "ЧЕРНЫЕ ПОБЕДИЛИ!"
        if surrendered:
            win_text += " (Сдача)"
        win = tk.Toplevel(self.root)
        win.title("Конец игры")
        w, h = int(self.board_w), int(self.board_h)
        x = (self.sw - w) // 2
        y = (self.sh - h) // 2
        win.geometry(f"{w}x{h}+{x}+{y}")
        win.configure(bg="#1a110a")
        win.transient(self.root)
        win.grab_set()
        big_font = ("Garamond", max(28, int(self.sh * 0.04)), "bold")
        btn_font = ("Verdana", max(14, int(self.sh * 0.02)), "bold")
        tk.Label(win, text=win_text, font=big_font, bg="#1a110a", fg="#00ff00").pack(pady=(h // 6, h // 12))
        tk.Label(win, text=f"Время партии: {mins:02d}:{secs:02d}", font=self.font_ui, bg="#1a110a", fg="white").pack(pady=15)
        tk.Button(
            win,
            text="В ГЛАВНОЕ МЕНЮ",
            font=btn_font,
            bg="#d4af37",
            fg="black",
            padx=40,
            pady=15,
            command=lambda: [win.destroy(), self.show_menu()],
        ).pack(pady=h // 6)


if __name__ == "__main__":
    root = tk.Tk()
    app = LongNardMaster(root)
    root.mainloop()