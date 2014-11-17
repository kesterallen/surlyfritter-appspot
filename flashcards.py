
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
import os
import random
import time 
import wsgiref.handlers

class FlashcardsHandler(webapp.RequestHandler):
    def generate_new_question(self, max_sum=15):
        the_sum = random.randint(1, max_sum)
        addend1 = the_sum - random.randint(1, the_sum)
        return addend1, the_sum

    def write_page(self, addend1, the_sum, message='', cards_done=0):
        template_file = 'flashcards.html'
        template_values = { 'message': message,
                            'addend1': addend1,
                            'the_sum': the_sum,
                            'cards_done': cards_done,
                          }
        template_text = str(template.render(
                                template_file,
                                template_values))
        self.response.out.write(template_text)

    def get(self, message=''):
        addend1, the_sum = self.generate_new_question()
        self.write_page(addend1, the_sum)

    def post(self):
        addend1 = int(self.request.get('addend1'))
        the_sum = int(self.request.get('the_sum'))
        cards_done = int(self.request.get('cards_done'))

        selects = self.request.get('select_values')
        print selects

        # Validate the form input is numeric:
        try:
            addend2 = self.request.get('addend2')
            # the float converts e.g. '3.0' to 3.0, which is then converted to 3
            addend2 = int(float(addend2)) 
        except:
            message = "'%s' is not a number! Try again:" % addend2
            self.write_page(addend1, the_sum, message, cards_done)
            return

        # Determine if the answer is correct, and generate a new question if 
        # it is:
        #
        is_right = the_sum == (addend1 + addend2)
        if is_right:
            # make a new question:
            cards_done += 1
            question_text = "question" if cards_done == 1 else "questions"
            message = ("""That's right: %s + %s = %s.
                       You've answered %s %s right!
                       Let's try another one!""" % (
                       addend1, addend2, the_sum, cards_done, question_text))
            addend1, the_sum = self.generate_new_question()
        else:
            message = "No, %s + %s does not = %s. Try again!" % (
                      addend1, addend2, the_sum)
        
        self.write_page(addend1, the_sum, message, cards_done)
        
            
def main():
    application = webapp.WSGIApplication(
                      [
                          ('/flashcards', FlashcardsHandler),
                          ('/',           FlashcardsHandler),
                      ],
                      debug=True
                  )
    wsgiref.handlers.CGIHandler().run(application)

if __name__ == "__main__":
    main()
