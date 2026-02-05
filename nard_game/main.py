import tkinter as tk
import random

WIDTH, HEIGHT = 1000, 750
MARGIN = 50
POINT_WIDTH = (WIDTH - 2 * MARGIN) // 13
PIECE_RADIUS = POINT_WIDTH // 2 - 5

#боты
def bot_easy(board, dice, color, calc_moves):
    moves_list = []
    for i in range(24):
        if board[i][1] == color:
            moves = calc_moves(i)
            for target, cost in moves.items():
                moves_list.append((i, target, cost))
    if moves_list:
        return random.choice(moves_list)
    return None

def bot_medium(board, dice, color, calc_moves):
    best_score = -1
    best_move = None
    for i in range(24):
        if board[i][1] == color:
            moves = calc_moves(i)
            for target, cost in moves.items():
                target_count, target_color = board[target]
                score = 1 if target_count == 0 or target_color == color else 0
                if score > best_score:
                    best_score = score
                    best_move = (i, target, cost)
    return best_move

def bot_hard(board, dice, color, calc_moves):
    best_score = -100
    best_move = None
    for i in range(24):
        if board[i][1] == color:
            moves = calc_moves(i)
            for target, cost in moves.items():
                target_count, target_color = board[target]
                score = 0
                if target_color and target_color != color:
                    score += 2
                else:
                    score += 1
                score += target if color == 'w' else (24 - target) % 24
                if score > best_score:
                    best_score = score
                    best_move = (i, target, cost)
    return best_move

class LongNardMaster:
    def __init__(self, root):
        self.root = root
        self.root.title("Длинные Нарды")
        self.root.configure(bg="#4B3621")
        
        self.reset_game_state()
        
        self.menu_frame = tk.Frame(root, bg="#4B3621")
        self.game_frame = tk.Frame(root, bg="#4B3621")
        
        self.canvas = tk.Canvas(self.game_frame, width=WIDTH, height=HEIGHT-100, bg="#b4855c", highlightthickness=0)
        self.lbl_info = tk.Label(self.game_frame, text="", font=("Arial", 16, "bold"), bg="#4B3621", fg="white")
        
        self.show_menu()

    def reset_game_state(self):
        self.board = [[0, None] for _ in range(24)]
        self.board[11] = [15, 'w']
        self.board[23] = [15, 'b']
        self.current_turn = 'w'
        self.dice = []
        self.head_taken = False 
        self.selected_point = None
        self.valid_moves = {}
        self.is_animating = False

    def show_menu(self):
        self.game_frame.pack_forget()
        self.menu_frame.pack(expand=True, fill=tk.BOTH)
        for widget in self.menu_frame.winfo_children(): widget.destroy()

        tk.Label(self.menu_frame, text="ДЛИННЫЕ НАРДЫ", font=("Arial", 36, "bold"), bg="#4B3621", fg="#D2B48C").pack(pady=40)
        modes = [("ИГРАТЬ ВДВОЕМ", None), ("БОТ: ЛЕГКИЙ", "easy"), ("БОТ: СРЕДНИЙ", "medium"), ("БОТ: СЛОЖНЫЙ", "hard")]
        for text, level in modes:
            tk.Button(self.menu_frame, text=text, width=25, font=("Arial", 12, "bold"),
                      command=lambda l=level: self.start_game(l)).pack(pady=10)

    def start_game(self, level):
        self.bot_level = level
        self.menu_frame.pack_forget()
        self.game_frame.pack()
        self.lbl_info.pack(pady=10)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", self.on_click)
        self.draw_board()
        self.root.after(1000, self.animate_dice)

    def get_target_index(self, start_idx, step):
        path = [11,10,9,8,7,6,5,4,3,2,1,0,23,22,21,20,19,18,17,16,15,14,13,12]
        try:
            curr_pos_in_path = path.index(start_idx)
            # движение по кругу
            target_pos_in_path = (curr_pos_in_path + step) % len(path)
            return path[target_pos_in_path]
        except ValueError:
            return None

    def calc_moves(self, start):
        moves = {}
        if not self.dice: return moves
        
        if self.head_taken and ((self.current_turn == 'w' and start == 11) or (self.current_turn == 'b' and start == 23)):
            return {}

        for d in set(self.dice):
            target = self.get_target_index(start, d)
            if self.board[target][0] == 0 or self.board[target][1] == self.current_turn:
                moves[target] = [d]

        if len(self.dice) >= 2:
            d1, d2 = self.dice[0], self.dice[1]
            mid = self.get_target_index(start, d1)
            target = self.get_target_index(start, d1 + d2)
            if mid and (self.board[mid][0] == 0 or self.board[mid][1] == self.current_turn):
                if self.board[target][0] == 0 or self.board[target][1] == self.current_turn:
                    moves[target] = [d1, d2]
        return moves

    def animate_dice(self):
        if self.is_animating or self.dice: return
        self.is_animating = True
        for i in range(10): self.root.after(i*80, self._dice_step, i)

    def _dice_step(self, step):
        temp = [random.randint(1,6), random.randint(1,6)]
        self.draw_board(temp_dice=temp)
        if step == 9:
            self.dice = temp
            if self.dice[0] == self.dice[1]: self.dice *= 2
            self.is_animating = False
            if not any(self.calc_moves(i) for i in range(24) if self.board[i][1] == self.current_turn):
                self.root.after(1000, self.next_turn)
            elif self.bot_level and self.current_turn == 'b':
                self.root.after(600, self.bot_move)

    def next_turn(self):
        self.current_turn = 'b' if self.current_turn == 'w' else 'w'
        self.head_taken = False
        self.dice = []
        self.lbl_info.config(text=f"Ход {'ЧЕРНЫХ' if self.current_turn=='b' else 'БЕЛЫХ'}")
        self.draw_board()
        self.root.after(600, self.animate_dice)

    def bot_move(self):
        bot_func = {'easy': bot_easy, 'medium': bot_medium, 'hard': bot_hard}[self.bot_level]
        move = bot_func(self.board, self.dice, self.current_turn, self.calc_moves)
        if move: self.animate_slide(*move)
        else: self.root.after(500, self.next_turn)

    def animate_slide(self, start, end, cost):
        self.is_animating = True
        sx, sy, sd = self.get_coords(start)
        ex, ey, ed = self.get_coords(end)
        s_pos = (sx + POINT_WIDTH/2, sy - sd*(PIECE_RADIUS + 5 + (self.board[start][0]-1)*15))
        e_pos = (ex + POINT_WIDTH/2, ey - ed*(PIECE_RADIUS + 5 + (self.board[end][0])*15))
        
        steps = 8
        for i in range(steps + 1):
            f = i / steps
            cx, cy = s_pos[0] + (e_pos[0]-s_pos[0])*f, s_pos[1] + (e_pos[1]-s_pos[1])*f
            self.root.after(i*20, lambda x=cx, y=cy: self.draw_board(moving={'x':x, 'y':y, 'col':self.board[start][1], 's':start}))
        self.root.after((steps+1)*20, lambda: self.complete_move(start, end, cost))

    def complete_move(self, start, end, cost):
        if (self.current_turn == 'w' and start == 11) or (self.current_turn == 'b' and start == 23):
            self.head_taken = True
        self.board[start][0] -= 1
        if self.board[start][0] == 0: self.board[start][1] = None
        self.board[end][0] += 1
        self.board[end][1] = self.current_turn
        for d in cost: 
            if d in self.dice: self.dice.remove(d)
        self.selected_point, self.valid_moves, self.is_animating = None, {}, False
        if not self.dice or not any(self.calc_moves(i) for i in range(24) if self.board[i][1] == self.current_turn):
            self.next_turn()
        elif self.bot_level and self.current_turn == 'b':
            self.root.after(400, self.bot_move)
        self.draw_board()

    def get_coords(self, index):
        if 0 <= index <= 11:
            x = WIDTH - MARGIN - (index + 1) * POINT_WIDTH
            if index >= 6: x -= 40
            return x, HEIGHT - 150, 1
        else:
            x = MARGIN + (index - 12) * POINT_WIDTH
            if (index - 12) >= 6: x += 40
            return x, MARGIN, -1

    def draw_board(self, temp_dice=None, moving=None):
        self.canvas.delete("all")
        for i in range(24):
            x, y, d = self.get_coords(i)
            col = "#8B4513" if i % 2 == 0 else "#D2B48C"
            self.canvas.create_polygon([x, y, x+POINT_WIDTH, y, x+POINT_WIDTH/2, y-d*220], fill=col, outline="black")
            if i in self.valid_moves:
                cx, cy = x + POINT_WIDTH/2, y + (5 if d == 1 else -5)
                self.canvas.create_oval(cx-8, cy-8, cx+8, cy+8, fill="#00FF00")
            cnt, pcol = self.board[i]
            if cnt > 0:
                for j in range(cnt):
                    if moving and moving['s'] == i and j == cnt-1: continue
                    px, py = x + POINT_WIDTH/2, y - d*(PIECE_RADIUS + 5 + j*15)
                    f, o = ("white", "black") if pcol == 'w' else ("black", "white")
                    self.canvas.create_oval(px-PIECE_RADIUS, py-PIECE_RADIUS, px+PIECE_RADIUS, py+PIECE_RADIUS, fill=f, outline=o)
        if moving:
            f = "white" if moving['col'] == 'w' else "black"
            self.canvas.create_oval(moving['x']-PIECE_RADIUS, moving['y']-PIECE_RADIUS, moving['x']+PIECE_RADIUS, moving['y']+PIECE_RADIUS, fill=f, outline="red", width=2)
        vals = temp_dice if temp_dice is not None else self.dice
        for i, v in enumerate(vals):
            bx, by = WIDTH//2 - 60 + i*45, HEIGHT//2 - 60
            self.canvas.create_rectangle(bx, by, bx+35, by+35, fill="white", outline="black")
            self.canvas.create_text(bx+17, by+17, text=str(v), font=("Arial", 14, "bold"))

    def on_click(self, event):
        if self.is_animating or (self.bot_level and self.current_turn == 'b'): return
        for i in range(24):
            x, y, d = self.get_coords(i)
            if x <= event.x <= x+POINT_WIDTH:
                if (d==1 and y-250 <= event.y <= y) or (d==-1 and y <= event.y <= y+250):
                    if i in self.valid_moves: self.animate_slide(self.selected_point, i, self.valid_moves[i])
                    elif self.board[i][1] == self.current_turn:
                        self.selected_point = i
                        self.valid_moves = self.calc_moves(i)
                        self.draw_board()
                    return

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry(f"{WIDTH}x{HEIGHT}")
    LongNardMaster(root)
    root.mainloop()
