
import yaml

def load_locale(filename):
    with open('locales/%s' % filename, 'r', encoding='utf-8') as file:
        return yaml.load(file.read(), yaml.Loader)

ru = load_locale('ru.yml')
en = load_locale('en.yml')

language_codes = ['ru', 'en']
