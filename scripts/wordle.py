# TODO: can't specify two locations for a "yes" letter, e.g. "L" in swill
BAD_LETTERS = "dieshorjoinsoldforge"
LETTERS = dict(
    a=dict(yes=1, no=[]),
    p=dict(yes=2, no=[]),
    u=dict(yes=3, no=[]),
    t=dict(yes=4, no=[]),
)


def get_words():
    words = []
    with open("/usr/share/dict/american-english") as lines:
        for line in lines:
            word = line.strip()
            if len(word) == 5 and "'" not in word and word.islower():
                words.append(word)
    return words


def letter_locations_good(word, letters):
    """
    Does the word have the right letters in the right locations, and not in the
    wrong places?
    """
    goods = []
    for letter, indices in letters.items():
        # Is the letter in the word at all?
        goods.append(letter in word)

        # If the letter's position is known, is it in the right place?
        if indices["yes"] is not None:
            goods.append(word[indices["yes"]] == letter)

        # If there are excluded spots for the letter, is it NOT there in this word?
        if indices["no"]:
            for index in indices["no"]:
                goods.append(word[index] != letter)
    return all(goods)


for word in get_words():
    no_bad_letters = all((l not in word for l in BAD_LETTERS))
    in_right_places = letter_locations_good(word, LETTERS)

    if no_bad_letters and in_right_places:
        print(word)
