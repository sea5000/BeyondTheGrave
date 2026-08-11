"""The interview guide: categories, why they matter, and seed questions.

The interviewer LLM uses this as a source of material. It never reads it verbatim -
it rephrases, follows threads, and asks follow-ups. Coverage per category drives
which topic gets asked next, and 'speech_style'/'phrases' feed the voice-cloning side.
"""

CATEGORIES = [
    ("identity", "Identity & self", 0.65),
    ("family", "Family", 0.7),
    ("friends", "Friends & community", 0.6),
    ("romance", "Love & relationships", 0.65),
    ("career", "Career & life's work", 0.6),
    ("life_events", "Life story & key events", 0.7),
    ("values", "Values & beliefs", 0.6),
    ("favorites", "Favorites & habits", 0.55),
    ("personality", "Personality & character", 0.6),
    ("speech_style", "Speech style & expressions", 0.6),
    ("wisdom", "Wisdom & messages", 0.55),
    ("phrases", "Sayings & catchphrases", 0.5),
]

GUIDE = {
    "identity": (
        "Core facts about who they are: full name, age/birthday, where they were born and grew up, "
        "how they see themselves, their name story.",
        [
            "What's your full name, and is there a story behind it?",
            "Where did you grow up, and what was that place like?",
            "How old are you, and how do you feel about that number?",
            "In three words, how would you describe yourself?",
            "What's the single most defining thing about you?",
        ],
    ),
    "family": (
        "Parents, siblings, grandparents, children - names, personalities, stories, relationships, "
        "traditions, and the moments that shaped these bonds.",
        [
            "Tell me about your family - who matters most to you?",
            "What was your relationship with your parents like?",
            "Do you have siblings? What's a memory you share?",
            "What family traditions did you grow up with?",
            "Who in your family knows you best, and why?",
            "What's something your family says about you?",
        ],
    ),
    "friends": (
        "Closest friends, the social circle, how friendships formed, shared history, what friendship means to them.",
        [
            "Who are your closest friends, and how did you meet them?",
            "What does a perfect day with friends look like for you?",
            "Who's the friend who's been through everything with you?",
            "How do you make and keep friends?",
        ],
    ),
    "romance": (
        "Romantic history, the significant other(s), how they met, love stories, what love means to them.",
        [
            "Tell me about the most important romantic relationship in your life.",
            "How did you two meet - the full story?",
            "What's something you'd want your partner to always remember?",
            "What does love mean to you?",
        ],
    ),
    "career": (
        "Jobs, calling, work that mattered, achievements, failures, the story of how they got here.",
        [
            "What have you done for work, and what did it mean to you?",
            "What are you proudest of accomplishing?",
            "What was a turning point in your career?",
            "If money didn't matter, what would you do with your time?",
        ],
    ),
    "life_events": (
        "Formative moments, losses, joys, travels, the peaks and valleys that made them.",
        [
            "What moments changed the course of your life?",
            "What's the hardest thing you've ever been through?",
            "What's the happiest moment you can remember?",
            "What place matters most to you, and why?",
            "Is there a moment you'd relive if you could?",
        ],
    ),
    "values": (
        "What they believe, what they stand for, what they'd fight for, faith, worldview, moral compass.",
        [
            "What do you believe in most strongly?",
            "What would you never compromise on?",
            "How does your faith or worldview shape you?",
            "What advice would your values give your younger self?",
        ],
    ),
    "favorites": (
        "Books, music, films, food, hobbies, routines, small pleasures - the texture of daily life.",
        [
            "What music do you love, and does a song remind you of someone?",
            "What book or film shaped how you think?",
            "What's a meal that feels like home?",
            "How do you spend a typical evening?",
            "What small pleasure do you never skip?",
        ],
    ),
    "personality": (
        "Temperament, humor, quirks, strengths, flaws, how others experience them.",
        [
            "What's your sense of humor like?",
            "What's a quirk or habit that's very you?",
            "What are you like on a bad day?",
            "What do people misunderstand about you?",
            "What are you most afraid of?",
        ],
    ),
    "speech_style": (
        "How they actually talk: pet phrases, verbal tics, tone, humor, words they overuse. "
        "Ask them for their exact words so the clone can sound like them.",
        [
            "What phrases or expressions do you say all the time?",
            "What's something you say that your friends would recognize as yours?",
            "How do you greet people, or end a conversation?",
            "What words do you overuse?",
            "If I recorded you for a day, what patterns would I hear?",
        ],
    ),
    "wisdom": (
        "What they've learned, the messages they'd leave behind, advice to loved ones, comfort they'd give.",
        [
            "What's the most important lesson life has taught you?",
            "If you could leave your loved ones one piece of advice, what would it be?",
            "What do you want people to remember about you?",
            "What would you say to comfort someone you love?",
        ],
    ),
    "phrases": (
        "Specific catchphrases, sayings, inside jokes, and words of love that define their spoken identity. "
        "These will be captured as recordings in their own voice.",
        [
            "What's a saying you live by?",
            "What's a phrase only your inner circle would understand?",
            "How do you tell someone you love them?",
            "What's your go-to toast or blessing?",
        ],
    ),
}
