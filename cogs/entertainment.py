"""
娛樂系統 Cog
猜數字、骰子、21點、剪刀石頭布、硬幣翻轉、8球、益智問答
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio

from config import Colors, Emoji, BadgeImages
from utils.embeds import EmbedFactory


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 21 點 Views
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CARD_VALUES = {
    "A": 11, "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7,
    "8": 8, "9": 9, "10": 10, "J": 10, "Q": 10, "K": 10,
}
SUITS = ["♠️", "♥️", "♦️", "♣️"]
CARD_NAMES = list(CARD_VALUES.keys())


def create_deck():
    return [(name, suit) for name in CARD_NAMES for suit in SUITS]


def hand_value(hand):
    total = sum(CARD_VALUES[card[0]] for card in hand)
    aces = sum(1 for card in hand if card[0] == "A")
    while total > 21 and aces:
        total -= 10
        aces -= 1
    return total


def format_hand(hand, hide_second=False):
    if hide_second and len(hand) >= 2:
        return f"{hand[0][0]}{hand[0][1]} 🂠"
    return " ".join(f"{c[0]}{c[1]}" for c in hand)


class BlackjackView(discord.ui.View):
    def __init__(self, player: discord.Member, deck: list, player_hand: list, dealer_hand: list):
        super().__init__(timeout=60)
        self.player = player
        self.deck = deck
        self.player_hand = player_hand
        self.dealer_hand = dealer_hand
        self.game_over = False

    def _build_embed(self, reveal_dealer=False) -> discord.Embed:
        embed = EmbedFactory.game("21 點")
        
        dealer_display = format_hand(self.dealer_hand, hide_second=not reveal_dealer)
        dealer_val = hand_value(self.dealer_hand) if reveal_dealer else f"? + {CARD_VALUES[self.dealer_hand[0][0]]}"
        embed.add_field(
            name=f"🤖 莊家 ({dealer_val})",
            value=f"```{dealer_display}```",
            inline=False,
        )
        
        player_val = hand_value(self.player_hand)
        embed.add_field(
            name=f"👤 {self.player.display_name} ({player_val})",
            value=f"```{format_hand(self.player_hand)}```",
            inline=False,
        )
        
        return embed

    async def _finish_game(self, interaction: discord.Interaction):
        """莊家回合 & 結算"""
        self.game_over = True
        
        # 莊家補牌
        while hand_value(self.dealer_hand) < 17:
            self.dealer_hand.append(self.deck.pop())
        
        player_val = hand_value(self.player_hand)
        dealer_val = hand_value(self.dealer_hand)
        
        embed = self._build_embed(reveal_dealer=True)
        
        if player_val > 21:
            result = "💥 爆牌！你輸了！"
            embed.color = Colors.ERROR
        elif dealer_val > 21:
            result = "🎉 莊家爆牌！你贏了！"
            embed.color = Colors.SUCCESS
        elif player_val > dealer_val:
            result = "🎉 你贏了！"
            embed.color = Colors.SUCCESS
        elif player_val < dealer_val:
            result = "😢 你輸了！"
            embed.color = Colors.ERROR
        else:
            result = "🤝 平手！"
            embed.color = Colors.WARNING
        
        embed.add_field(name="**結果**", value=f"**{result}**", inline=False)
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.primary, emoji="🃏")
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("這不是你的遊戲！", ephemeral=True)
        
        self.player_hand.append(self.deck.pop())
        
        if hand_value(self.player_hand) >= 21:
            await self._finish_game(interaction)
        else:
            embed = self._build_embed()
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.success, emoji="✋")
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("這不是你的遊戲！", ephemeral=True)
        
        await self._finish_game(interaction)

    @discord.ui.button(label="Double Down", style=discord.ButtonStyle.danger, emoji="💰")
    async def double_down(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("這不是你的遊戲！", ephemeral=True)
        
        self.player_hand.append(self.deck.pop())
        await self._finish_game(interaction)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 剪刀石頭布 View
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class RPSView(discord.ui.View):
    def __init__(self, player: discord.Member):
        super().__init__(timeout=30)
        self.player = player

    async def _play(self, interaction: discord.Interaction, choice: str):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("這不是你的遊戲！", ephemeral=True)
        
        choices = ["✂️ 剪刀", "🪨 石頭", "📄 布"]
        choice_map = {"scissors": 0, "rock": 1, "paper": 2}
        
        player_idx = choice_map[choice]
        bot_idx = random.randint(0, 2)
        
        player_choice = choices[player_idx]
        bot_choice = choices[bot_idx]
        
        if player_idx == bot_idx:
            result = "🤝 平手！"
            color = Colors.WARNING
        elif (player_idx - bot_idx) % 3 == 1:
            result = "🎉 你贏了！"
            color = Colors.SUCCESS
        else:
            result = "😢 你輸了！"
            color = Colors.ERROR
        
        embed = EmbedFactory.game("剪刀石頭布")
        embed.color = color
        embed.add_field(name="你的選擇", value=player_choice, inline=True)
        embed.add_field(name="Bot 的選擇", value=bot_choice, inline=True)
        embed.add_field(name="結果", value=f"**{result}**", inline=False)
        
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="剪刀", style=discord.ButtonStyle.primary, emoji="✂️")
    async def scissors(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "scissors")

    @discord.ui.button(label="石頭", style=discord.ButtonStyle.primary, emoji="🪨")
    async def rock(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "rock")

    @discord.ui.button(label="布", style=discord.ButtonStyle.primary, emoji="📄")
    async def paper(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._play(interaction, "paper")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 猜數字 View
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class GuessModal(discord.ui.Modal, title="猜數字"):
    guess = discord.ui.TextInput(
        label="輸入你的猜測 (1-100)",
        placeholder="輸入一個數字...",
        min_length=1,
        max_length=3,
    )

    def __init__(self, view: "GuessView"):
        super().__init__()
        self.guess_view = view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            num = int(self.guess.value)
        except ValueError:
            return await interaction.response.send_message("請輸入有效的數字！", ephemeral=True)
        
        self.guess_view.attempts += 1
        
        if num == self.guess_view.target:
            embed = EmbedFactory.game("🎉 猜對了！", f"答案是 **{self.guess_view.target}**！\n你猜了 **{self.guess_view.attempts}** 次")
            embed.color = Colors.SUCCESS
            for item in self.guess_view.children:
                item.disabled = True
            await interaction.response.edit_message(embed=embed, view=self.guess_view)
        elif num < self.guess_view.target:
            embed = EmbedFactory.game("猜數字", f"🔼 **太低了！** 再高一點\n目前猜了 `{self.guess_view.attempts}` 次\n範圍：`{max(self.guess_view.low, num + 1)}` - `{self.guess_view.high}`")
            self.guess_view.low = max(self.guess_view.low, num + 1)
            await interaction.response.edit_message(embed=embed)
        else:
            embed = EmbedFactory.game("猜數字", f"🔽 **太高了！** 再低一點\n目前猜了 `{self.guess_view.attempts}` 次\n範圍：`{self.guess_view.low}` - `{min(self.guess_view.high, num - 1)}`")
            self.guess_view.high = min(self.guess_view.high, num - 1)
            await interaction.response.edit_message(embed=embed)


class GuessView(discord.ui.View):
    def __init__(self, player: discord.Member):
        super().__init__(timeout=120)
        self.player = player
        self.target = random.randint(1, 100)
        self.attempts = 0
        self.low = 1
        self.high = 100

    @discord.ui.button(label="猜一個數字", style=discord.ButtonStyle.primary, emoji="🔢")
    async def guess_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.player.id:
            return await interaction.response.send_message("這不是你的遊戲！", ephemeral=True)
        
        modal = GuessModal(self)
        await interaction.response.send_modal(modal)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 主要 Cog
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

class Entertainment(commands.GroupCog, name="fun", description="🎮 娛樂與迷你遊戲系統"):
    """娛樂系統 — 迷你遊戲"""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="guess", description="猜數字遊戲 (1-100)")
    async def guess(self, interaction: discord.Interaction):
        embed = EmbedFactory.game("猜數字", "我想了一個 1-100 之間的數字，試試猜猜看！\n點擊下方按鈕開始猜測。")
        view = GuessView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="dice", description="擲骰子")
    @app_commands.describe(sides="骰子面數（預設 6）")
    async def dice(self, interaction: discord.Interaction, sides: int = 6):
        if sides < 2 or sides > 100:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("面數無效", "請輸入 2-100 之間的數字。"),
                ephemeral=True,
            )
        
        result = random.randint(1, sides)
        
        # 骰子動畫
        dice_emojis = ["🎲", "🎯", "💫", "✨"]
        
        embed = EmbedFactory.game(f"{Emoji.DICE} 擲骰子")
        embed.add_field(name="**骰子**", value=f"`{sides}` 面骰", inline=True)
        embed.add_field(name="**結果**", value=f"# {result}", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="blackjack", description="21 點紙牌遊戲")
    async def blackjack(self, interaction: discord.Interaction):
        deck = create_deck()
        random.shuffle(deck)
        
        player_hand = [deck.pop(), deck.pop()]
        dealer_hand = [deck.pop(), deck.pop()]
        
        view = BlackjackView(interaction.user, deck, player_hand, dealer_hand)
        embed = view._build_embed()
        
        # 檢查天然 21 點
        if hand_value(player_hand) == 21:
            embed = view._build_embed(reveal_dealer=True)
            embed.add_field(name="**結果**", value="**🎉 天然 21 點！你贏了！**", inline=False)
            embed.color = Colors.SUCCESS
            for item in view.children:
                item.disabled = True
        
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="rps", description="剪刀石頭布")
    async def rps(self, interaction: discord.Interaction):
        embed = EmbedFactory.game("剪刀石頭布", "選擇你的出招！")
        view = RPSView(interaction.user)
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="coinflip", description="硬幣翻轉")
    async def coinflip(self, interaction: discord.Interaction):
        result = random.choice(["正面", "反面"])
        emoji = "🪙" if result == "正面" else "💿"
        
        embed = EmbedFactory.game("硬幣翻轉")
        embed.add_field(name="結果", value=f"# {emoji} {result}", inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="8ball", description="神奇 8 號球")
    @app_commands.describe(question="你的問題")
    async def eightball(self, interaction: discord.Interaction, question: str):
        responses = [
            # 正面
            "✅ 毫無疑問", "✅ 確定是的", "✅ 毫無懸念",
            "✅ 是的，一定", "✅ 你可以依靠它", "✅ 在我看來，是的",
            "✅ 很有可能", "✅ 展望良好", "✅ 跡象指向是",
            # 中立
            "🔮 回覆模糊，再試一次", "🔮 稍後再問",
            "🔮 現在最好不告訴你", "🔮 無法預測",
            "🔮 集中精神再問一次",
            # 負面
            "❌ 別指望了", "❌ 我的回答是否", "❌ 消息來源說不是",
            "❌ 展望不太好", "❌ 非常懷疑",
        ]
        
        answer = random.choice(responses)
        
        embed = discord.Embed(
            title=f"{Emoji.MAGIC} 神奇 8 號球",
            color=Colors.MUSIC,
        )
        if BadgeImages.GAME:
            embed.set_thumbnail(url=BadgeImages.GAME)
        embed.add_field(name="**你的問題**", value=f"*{question}*", inline=False)
        embed.add_field(name="**回答**", value=f"**{answer}**", inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="trivia", description="益智問答")
    async def trivia(self, interaction: discord.Interaction):
        questions = [
            {
                "q": "地球上最深的海溝是？",
                "options": ["馬里亞納海溝", "日本海溝", "菲律賓海溝", "湯加海溝"],
                "answer": 0,
            },
            {
                "q": "人體最大的器官是？",
                "options": ["肝臟", "皮膚", "大腦", "腸道"],
                "answer": 1,
            },
            {
                "q": "光速大約是每秒多少公里？",
                "options": ["100,000", "200,000", "300,000", "400,000"],
                "answer": 2,
            },
            {
                "q": "世界上最長的河流是？",
                "options": ["亞馬遜河", "尼羅河", "長江", "密西西比河"],
                "answer": 1,
            },
            {
                "q": "Discord 是在哪一年推出的？",
                "options": ["2013", "2014", "2015", "2016"],
                "answer": 2,
            },
            {
                "q": "Python 程式語言是誰創造的？",
                "options": ["James Gosling", "Guido van Rossum", "Bjarne Stroustrup", "Dennis Ritchie"],
                "answer": 1,
            },
            {
                "q": "地球到太陽的平均距離大約是？",
                "options": ["1 億公里", "1.5 億公里", "2 億公里", "2.5 億公里"],
                "answer": 1,
            },
            {
                "q": "世界上面積最大的國家是？",
                "options": ["加拿大", "中國", "美國", "俄羅斯"],
                "answer": 3,
            },
        ]
        
        q = random.choice(questions)
        
        embed = EmbedFactory.game("益智問答", f"**{q['q']}**")
        
        view = TriviaView(interaction.user, q)
        
        for i, opt in enumerate(q["options"]):
            embed.add_field(
                name=f"{['🅰️', '🅱️', '🅲', '🅳'][i]} {opt}",
                value="\u200b",
                inline=True,
            )
        
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="slots", description="拉霸老虎機遊戲")
    async def slots(self, interaction: discord.Interaction):
        emojis = ["🍒", "🍇", "🍋", "🍊", "🔔", "💎", "⭐", "7️⃣"]
        embed = EmbedFactory.game("🎰 老虎機", "【 🎰 | 🎰 | 🎰 】\n\n*拉動拉桿中...*")
        await interaction.response.send_message(embed=embed)
        
        # 模擬 3 次滾動效果
        for i in range(3):
            await asyncio.sleep(0.5)
            r1 = random.choice(emojis)
            r2 = random.choice(emojis)
            r3 = random.choice(emojis)
            embed.description = f"【 {r1} | {r2} | {r3} 】\n\n*轉動中...*"
            await interaction.edit_original_response(embed=embed)
            
        await asyncio.sleep(0.5)
        r1 = random.choice(emojis)
        r2 = random.choice(emojis)
        r3 = random.choice(emojis)
        
        # 判斷勝負
        if r1 == r2 == r3:
            if r1 == "7️⃣":
                result = "🔥 恭喜獲得超級大獎 (JACKPOT)！大三元 777！"
                embed.color = Colors.GIVEAWAY
            elif r1 == "💎":
                result = "💎 恭喜獲得鑽石大獎！三連鑽石！"
                embed.color = Colors.SUCCESS
            else:
                result = f"🎉 恭喜連線成功！獲得 {r1} 三連線！"
                embed.color = Colors.SUCCESS
        elif r1 == r2 or r2 == r3 or r1 == r3:
            result = "✨ 差一點點！兩連線，獲得小獎！"
            embed.color = Colors.WARNING
        else:
            result = "😢 很遺憾，沒有連線成功。再試一次吧！"
            embed.color = Colors.ERROR
            
        embed.description = f"【 {r1} | {r2} | {r3} 】\n\n**{result}**"
        await interaction.edit_original_response(embed=embed)

    @app_commands.command(name="roll", description="擲骰子（支援公式如 2d10+5、3d6）")
    @app_commands.describe(formula="骰子公式（例如：2d10+5，預設 1d6）")
    async def roll(self, interaction: discord.Interaction, formula: str = "1d6"):
        import re
        pattern = r"^(?P<num>\d*)d(?P<sides>\d+)(?P<mod>[+-]\d+)?$"
        match = re.match(pattern, formula.strip().replace(" ", "").lower())
        
        if not match:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("公式格式錯誤", "正確格式例如：`3d6`、`2d10+5`、`d20-3`"),
                ephemeral=True
            )
            
        num_str = match.group("num")
        num = int(num_str) if num_str else 1
        sides = int(match.group("sides"))
        mod_str = match.group("mod")
        mod = int(mod_str) if mod_str else 0
        
        if num < 1 or num > 50:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("數量無效", "骰子數量最多為 50 個。"),
                ephemeral=True
            )
        if sides < 2 or sides > 1000:
            return await interaction.response.send_message(
                embed=EmbedFactory.error("面數無效", "骰子面數介於 2 到 1000 之間。"),
                ephemeral=True
            )
            
        rolls = [random.randint(1, sides) for _ in range(num)]
        rolls_sum = sum(rolls)
        total = rolls_sum + mod
        
        rolls_detail = ", ".join(map(str, rolls))
        mod_sign = f"+{mod}" if mod > 0 else f"{mod}" if mod < 0 else ""
        formula_display = f"{num}d{sides}{mod_sign}"
        
        embed = EmbedFactory.game(f"{Emoji.DICE} 擲骰公式：{formula_display}")
        embed.add_field(name="**擲骰結果明細**", value=f"[{rolls_detail}]", inline=False)
        if mod != 0:
            embed.add_field(name="**擲骰總和**", value=f"`{rolls_sum}` {mod_sign}", inline=True)
        embed.add_field(name="**最終總計**", value=f"# {total}", inline=True)
        
        await interaction.response.send_message(embed=embed)


class TriviaView(discord.ui.View):
    def __init__(self, player: discord.Member, question: dict):
        super().__init__(timeout=30)
        self.player = player
        self.question = question
        self.answered = False
        
        labels = ["🅰️", "🅱️", "🅲", "🅳"]
        for i, opt in enumerate(question["options"]):
            button = discord.ui.Button(
                label=opt,
                style=discord.ButtonStyle.secondary,
                custom_id=f"trivia_{i}",
                emoji=labels[i],
            )
            button.callback = self._make_callback(i)
            self.add_item(button)

    def _make_callback(self, index: int):
        async def callback(interaction: discord.Interaction):
            if interaction.user.id != self.player.id:
                return await interaction.response.send_message("這不是你的問答！", ephemeral=True)
            if self.answered:
                return
            self.answered = True
            
            correct = index == self.question["answer"]
            
            embed = EmbedFactory.game("益智問答")
            embed.add_field(name="**問題**", value=self.question["q"], inline=False)
            
            if correct:
                embed.add_field(name="**結果**", value="🎉 **答對了！**", inline=False)
                embed.color = Colors.SUCCESS
            else:
                correct_answer = self.question["options"][self.question["answer"]]
                embed.add_field(
                    name="**結果**",
                    value=f"❌ **答錯了！**\n正確答案：**{correct_answer}**",
                    inline=False,
                )
                embed.color = Colors.ERROR
            
            for item in self.children:
                item.disabled = True
                if isinstance(item, discord.ui.Button):
                    btn_idx = int(item.custom_id.split("_")[1])
                    if btn_idx == self.question["answer"]:
                        item.style = discord.ButtonStyle.success
                    elif btn_idx == index and not correct:
                        item.style = discord.ButtonStyle.danger
            
            await interaction.response.edit_message(embed=embed, view=self)
        
        return callback

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 笑話 / 語錄 / 趣味小指令
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    JOKES = [
        "為什麼程式設計師總是分不清萬聖節和聖誕節？\n因為 Oct 31 == Dec 25 🎃🎄",
        "我跟我的 Bug 說：「你為什麼不離開我？」\nBug 說：「因為你 catch 不到我啊！」🐛",
        "為什麼 Java 程式設計師需要戴眼鏡？\n因為他們看不到 C#  👓",
        "程式設計師不是在修 Bug，就是在製造 Bug 的路上 🚀",
        "有人問我什麼是遞迴？\n我說：請看這則笑話 🔄",
        "我的密碼超安全的！\n因為連我自己都記不住 🔐",
        "Why do programmers prefer dark mode?\nBecause light attracts bugs! 🦟",
        "電腦：你有 99 個問題\n程式設計師：修了一個\n電腦：你現在有 142 個問題 💀",
        "人生就像 Git，有太多的 conflict 要 resolve 😩",
        "為什麼魚不會打電腦？因為怕上網 🐟",
        "什麼動物最會存錢？小豬 🐷（撲滿）",
        "你知道最會騙人的星座是什麼嗎？說謊座（射手座）🏹",
        "為什麼海水是鹹的？因為魚都在裡面流汗 🐠💦",
    ]

    QUOTES = [
        "「成功不是最終的，失敗也不是致命的，勇氣才是最重要的。」— 邱吉爾 💪",
        "「昨天的你已經過去了，明天的你還沒到來，今天的你最重要。」🌟",
        "「唯一限制你的是你自己。」— 愛因斯坦 🧠",
        "「不是因為困難而不敢嘗試，而是因為不敢嘗試才覺得困難。」🚀",
        "「學習是一座金礦，挖之不盡，用之不竭。」📚",
        "「努力不一定成功，但放棄一定失敗。」🔥",
        "「你不需要很厲害才能開始，但你需要開始才能變得很厲害。」⭐",
        "「每天進步一點點，一年後你會感謝今天的自己。」📈",
        "「做你害怕的事，恐懼就會消失。」🦁",
        "「生活不是等待暴風雨過去，而是學會在雨中跳舞。」☔💃",
    ]

    @app_commands.command(name="joke", description="😂 隨機笑話")
    async def joke(self, interaction: discord.Interaction):
        embed = EmbedFactory.game("隨機笑話 😂")
        embed.description = random.choice(self.JOKES)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="quote", description="📜 隨機勵志語錄")
    async def quote(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="📜 今日語錄",
            description=random.choice(self.QUOTES),
            color=Colors.PRIMARY,
        )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="choose", description="🤔 幫你從多個選項中隨機選一個")
    @app_commands.describe(choices="以 ; 分隔的選項，例如 吃飯;睡覺;打 code")
    async def choose(self, interaction: discord.Interaction, choices: str):
        options = [opt.strip() for opt in choices.split(";") if opt.strip()]
        if len(options) < 2:
            return await interaction.response.send_message("❌ 請至少提供 2 個選項！", ephemeral=True)
        chosen = random.choice(options)
        embed = EmbedFactory.game("幫你選！ 🤔")
        embed.description = f"在 {len(options)} 個選項中，我選了...\n\n🎯 **{chosen}**"
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="emoji_rain", description="🌧️ 下表情符號雨！")
    @app_commands.describe(emoji="要下雨的表情符號（預設隨機）", count="表情數量（最多 30）")
    async def emoji_rain(self, interaction: discord.Interaction, emoji: str = None, count: int = 10):
        count = max(1, min(count, 30))
        rain_emojis = ["🌧️", "⛈️", "🌊", "💧", "🌈", "⭐", "❄️", "🎉", "🌸", "💜", "🔥", "🎵"]
        chosen_emoji = emoji or random.choice(rain_emojis)
        rain = " ".join([chosen_emoji] * count)
        await interaction.response.send_message(f"🌧️ **表情雨！**\n{rain}")


async def setup(bot: commands.Bot):
    await bot.add_cog(Entertainment(bot))

