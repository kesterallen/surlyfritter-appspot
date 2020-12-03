
from Parents import RequestHandlerParent
from utils import render_template_text
import logging

class RecipesHandler(RequestHandlerParent):
    """Serve a recipe, or the index of recipies"""

    PANCAKES = set([
        'pancakes',
        'buttermilks',
        'flapjacks',
        'hotcakes',
        'griddlecakes',
        'johnnycakes',
        'pancake',
        'buttermilk',
        'flapjack',
        'hotcake',
        'griddlecake',
        'johnnycake',
    ])
    SOURDOUGH_PANCAKES = set([
        'sourdough',
        'sourdough-pancakes',
        'sourdough_pancakes',
    ])
    WAFFLES = set([
        'waffles',
        'yogurt-wafffles',
        'yogurt_wafffles',
    ])
    OATMEAL = set([
        'oats',
        'oatmeal',
        'steel_cut_oatmeal',
        'steel_cut_oats',
        'porrridge',
    ])
    PANEER = set([
        'paneer',
        'mutar-paneer',
        'matar-paneer',
        'mutar_paneer',
        'matar_paneer',
        'mutar',
        'matar',
    ])
    PRETZEL_PIE = set([
        'pretzel_pie',
        'pretzel-pie',
        'pretzelpie',
    ])
    KEYLIME_PIE = set([
        'key_lime_pie',
        'keylimepie',
        'key_lime',
        'keylime',
    ])
    FRUIT_CRISP = set([
        'fruit_crisp',
        'plum_crisp',
        'crisp',
    ])
    MEXICAN_RICE = set([
        'rice',
        'mexican_rice',
        'mexican-rice',
        'instant_pot_mexican_rice',
        'instant-pot-mexican-rice',
    ])
    MUJADARA = set([
        'mujadara',
        'lentils',
    ])
    PUMPKIN_PIE = set([
        'libbys',
        'libby',
        'pumpkin',
        'pumpkin_pie',
    ])

    @property
    def recipe_values(self):
        logging.info("Recipe name: {}".format(self.recipe_name))
        if self.recipe_name in RecipesHandler.PANCAKES:
            url = "buttermilk_pancakes.html"
            title = "All-buttermilk pancakes"
            subtitle = "Best pancake recipe"
        elif self.recipe_name in RecipesHandler.SOURDOUGH_PANCAKES:
            url = "sourdough_pancakes.html"
            title = "Sourdough-buttermilk pancakes"
            subtitle = "Good pancake recipe"
        elif self.recipe_name in RecipesHandler.WAFFLES:
            url = "yogurt_waffles.html"
            title = "Yogurt waffles"
            subtitle = "Good waffles recipe"
        elif self.recipe_name in RecipesHandler.OATMEAL:
            url = "instant_pot_steel_cut_oatmeal.html"
            title = "Steel-Cut Instant Pot Oatmeal"
            subtitle = "Steel-Cut oatmeal, easy"
        elif self.recipe_name in RecipesHandler.PANEER:
            url = "mutar_paneer.html"
            title = "Mutar Paneer"
            subtitle = "Mutar Paneer"
        elif self.recipe_name in RecipesHandler.PRETZEL_PIE:
            url = "strawberry_pretzel_pie.html"
            title = "Strawberry Prezel Pie"
            subtitle = "from https://cooking.nytimes.com/recipes/1020323-strawberry-pretzel-pie"
        elif self.recipe_name in RecipesHandler.KEYLIME_PIE:
            url = "key_lime_pie.html"
            title = "Key Lime Pie"
            subtitle = "Recipe courtesy of Joe's Stone Crab"
        elif self.recipe_name in RecipesHandler.FRUIT_CRISP:
            url = "fruit_crisp.html"
            title = "Fruit Crisp"
            subtitle = "easy"
        elif self.recipe_name in RecipesHandler.MEXICAN_RICE:
            url = "instant_pot_mexican_rice.html"
            title = "Mexican Rice (Instant Pot)"
            subtitle = ""
        elif self.recipe_name in RecipesHandler.MUJADARA:
            url = "mujadara.html"
            title = "Mujadara"
            subtitle = ""
        elif self.recipe_name in RecipesHandler.PUMPKIN_PIE:
            url = "pumpkin_pie.html"
            title = "Pumpkin Pie"
            subtitle = "Libbys Famous"
        else:
            url = "recipes.html"
            title = "Recipes List"
            subtitle = "Recipes List"

        return dict(url=url, title=title, subtitle=subtitle)

    @property
    def url_end(self):
        return self.recipe_values['url']

    def get(self, recipe_name=None):
        self.recipe_name = recipe_name
        page = render_template_text(self.url_end, self.recipe_values,
            subdirectory="templates/recipes")
        self.write_output(page)

class PancakesHandler(RecipesHandler):
    def get(self):
        super(PancakesHandler, self).get(recipe_name="pancakes")
