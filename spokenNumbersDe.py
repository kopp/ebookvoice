#!/usr/bin/python

'''Spell (German) numbers.'''

import re
import math
import unittest


class Number():

    def __init__(self, string, is_ordinal=False):
        '''
        Parse the number from string (may be a number as well) and store it
        internally.  Removes any non-numeric parts.

        Set is_ordinal to True, when the number is an ordinal number.
        '''
        try:
            self._value = int(string)
        except ValueError:
            self._value = int(re.sub('[^0-9]', '', string))
        self._is_ordinal = is_ordinal

    EXCEPTIONS_ORDINALS = {
            0: 'nullte',
            1: 'erste',
            3: 'dritte',
            8: 'achte',
            }

    EXCEPTIONS = {
            0: 'null',
            1: 'eins',
            }

    PRIMITIVES = {
            1: 'ein',
            2: 'zwei',
            3: 'drei',
            4: 'vier',
            5: 'fünf',
            6: 'sechs',
            7: 'sieben',
            8: 'acht',
            9: 'neun',
            10: 'zehn',
            11: 'elf',
            12: 'zwölf',
            16: 'sechzehn',
            17: 'siebzehn',
            }

    TENS = {
            10: 'zehn',
            20: 'zwanzig',
            30: 'dreißig',
            40: 'vierzig',
            50: 'fünfzig',
            60: 'sechzig',
            70: 'siebzig',
            80: 'achtzig',
            90: 'neunzig',
            }

    POWERS = {
            10: 'zehn',
            100: 'hundert',
            1000: 'tausend',
            1000000: 'millionen',
            }

    @staticmethod
    def _get_power(number, power):
        '''Return decimal position denoted by power (e.g. 3 from 2315 for power=2).'''
        return (number // (10**power)) % 10

    @staticmethod
    def _get_some_powers(number, smallest_power, number_decimals=3):
        '''Return the three (default, adjust with number_decimals) decimal numbers to the given power and two higher ones.'''
        digits = 0
        for i in range(number_decimals):
            digits += Number._get_power(number, smallest_power + i) * 10**i
        return digits

    def _get_max_power(number):
        '''Get highest power necessary to parse number (e.g. 4 for 31013).'''
        return int(math.log(number) / math.log(10))

    @staticmethod
    def _spell_regular(number):
        '''Spell the given number that is formed 'regularly'.'''
        try:
            return Number.PRIMITIVES[number]
        except KeyError:
            try:
                return Number.TENS[number]
            except KeyError:
                if number < 20:
                    return Number._spell_regular(Number._get_power(number, 0)) + Number.TENS[10]
                elif number < 100:
                    return Number._spell_regular(Number._get_power(number, 0)) + 'und' + \
                            Number.TENS[10 * Number._get_power(number, 1)]
                else:
                    millionen = Number._get_some_powers(number, 6)
                    tausender = Number._get_some_powers(number, 3)
                    hunderter = Number._get_power(number, 2)
                    rest = Number._get_some_powers(number, 0, 2)
                    #print('large number decomposed to {}, {}, {}, {}'.format(millionen, tausender, hunderter, rest))
                    string = ''
                    if millionen:
                        if millionen == 1:
                            string += 'einemillion'
                        else:
                            string += Number._spell_regular(millionen) + Number.POWERS[1000000]
                    if tausender:
                        string += Number._spell_regular(tausender) + Number.POWERS[1000]
                    if hunderter:
                        string += Number._spell_regular(hunderter) + Number.POWERS[100]
                    if rest:
                        string += Number._spell(rest)
                    return string



    @staticmethod
    def _spell_ordinal(number):
        try:
            return Number.EXCEPTIONS_ORDINALS[number]
        except KeyError:
            spelled = Number._spell(number)
            ending = None
            if number < 20:
                ending = 'te'
            else:
                ending = 'ste'
            return spelled + ending


    @staticmethod
    def _spell(number):
        try:
            return Number.EXCEPTIONS[number]
        except KeyError:
            # hack for years
            if 1000 < number < 2000:
                return Number._spell(Number._get_some_powers(number, 2, 2)) + 'hundert' + \
                        Number._spell(Number._get_some_powers(number, 0, 2))
            else:
                return Number._spell_regular(number)

    def spell(self):
        '''Spell the stored number.'''
        if self._is_ordinal:
            return Number._spell_ordinal(self._value)
        else:
            return Number._spell(self._value)



class Text():

    def __init__(self, string):
        '''Initialize text with a string.'''
        self._string = string

    NUMBER_RE = re.compile(r'([0-9]+)(,[0-9]+)?')
    # ordinals must be followed by non-noun (minuscule); otherwise they might
    # get confused with end-of-sentence
    ORDINAL_RE = re.compile(r'([0-9]+)\.( +[a-z])')
    ORDINALS_MONTH_RE = re.compile(r'([0-9]+)\. +(Jan|Feb|Mär|Apr|Mai|Jun|Jul|Aug|Sep|Okt|Nov|Dez)')
    UNITS_RE = re.compile(r'([0-9]+),([0-9]{2}) (Euro|Meter)')
    SPLIT_NUMBERS_RE = re.compile(r'([0-9])\s+([0-9]{3})')

    @staticmethod
    def _speak_units(finding):
        before_comma = Number(finding.group(1))
        after_comma = Number(finding.group(2))
        unit_name = finding.group(3)
        return before_comma.spell() + ' ' + unit_name + ' ' + after_comma.spell()

    @staticmethod
    def _speak_numbers(finding):
        number = Number(finding.group(1))
        spoken = number.spell()
        # check, if there is something behind the comma
        comma = finding.group(2)
        if comma:
            number2 = Number(comma)
            spoken += ' Komma ' + number2.spell()
        return spoken

    @staticmethod
    def _remove_space(finding):
        return finding.group(1) + finding.group(2)

    @staticmethod
    def _speak_ordinal(finding):
        ordinal = Number(finding.group(1), True)
        rest = finding.group(2)
        return ordinal.spell() + rest

    @staticmethod
    def _speak_ordinal_month(finding):
        ordinal = Number(finding.group(1), True)
        rest = finding.group(2)
        return ordinal.spell() + 'r ' + rest


    def speak_numbers(self):
        '''Substitute the numbers in the stored string to their textual
        representation, return a string with substituted numbers.'''
        string = self._string
        # remove spaces between numbers
        string = Text.SPLIT_NUMBERS_RE.sub(Text._remove_space, string)
        # first, substitute units
        string = Text.UNITS_RE.sub(Text._speak_units, string)
        # then ordinals
        string = Text.ORDINALS_MONTH_RE.sub(Text._speak_ordinal_month, string)
        string = Text.ORDINAL_RE.sub(Text._speak_ordinal, string)
        # then substitute all other numbers
        string = Text.NUMBER_RE.sub(Text._speak_numbers, string)
        return string



def spell_numbers(string):
    '''Substitue textual numbers with their spelled out version.'''
    t = Text(string)
    return t.speak_numbers()




## tests


class TestTextMethods(unittest.TestCase):

    def compare(self, before, after):
        t = Text(before)
        self.assertEqual(t.speak_numbers(), after)

    def test_numbers(self):
        self.compare('foo 13 bar', 'foo dreizehn bar')

    def test_units(self):
        self.compare('foo 13,60 Euro bar', 'foo dreizehn Euro sechzig bar')
        self.compare('foo 13,60 Meter bar', 'foo dreizehn Meter sechzig bar')

    def test_remove_space(self):
        self.compare('foo 13 400 bar', 'foo dreizehntausendvierhundert bar')
        self.compare('foo 13 40 bar', 'foo dreizehn vierzig bar')

    def test_ordinals(self):
        self.compare('foo 14. bar', 'foo vierzehnte bar')
        self.compare('foo 14. Bar', 'foo vierzehn. Bar')

    def test_ordinals_month(self):
        self.compare('foo 14. November', 'foo vierzehnter November')

    def test_commas(self):
        self.compare('foo 1,5 bar', 'foo eins Komma fünf bar')
        self.compare('foo 1, 5 bar', 'foo eins, fünf bar')
        self.compare('foo 1,0 bar', 'foo eins Komma null bar')
        self.compare('foo 13,42 bar', 'foo dreizehn Komma zweiundvierzig bar')
        # TODO: make it 'foo dreizehn Komma vier zwei bar')



class TestNumberMethods(unittest.TestCase):

    def dict_test(self, dictionary, is_ordinal=False):
        '''Run a test on a dictionary with number -> spelled number.'''
        for i,j in dictionary.items():
            n = Number(i, is_ordinal)
            self.assertEqual(n.spell(), j)

    def test_toTwenty(self):
        result = {
                0: 'null',
                1: 'eins',
                2: 'zwei',
                3: 'drei',
                4: 'vier',
                5: 'fünf',
                6: 'sechs',
                7: 'sieben',
                8: 'acht',
                9: 'neun',
                10: 'zehn',
                11: 'elf',
                12: 'zwölf',
                13: 'dreizehn',
                14: 'vierzehn',
                15: 'fünfzehn',
                16: 'sechzehn',
                17: 'siebzehn',
                18: 'achtzehn',
                19: 'neunzehn',
                }
        self.dict_test(result)

    def test_toHundred(self):
        result = {
                20: 'zwanzig',
                21: 'einundzwanzig',
                22: 'zweiundzwanzig',
                23: 'dreiundzwanzig',
                24: 'vierundzwanzig',
                25: 'fünfundzwanzig',
                26: 'sechsundzwanzig',
                27: 'siebenundzwanzig',
                28: 'achtundzwanzig',
                29: 'neunundzwanzig',
                30: 'dreißig',
                31: 'einunddreißig',
                32: 'zweiunddreißig',
                33: 'dreiunddreißig',
                40: 'vierzig',
                41: 'einundvierzig',
                42: 'zweiundvierzig',
                50: 'fünfzig',
                60: 'sechzig',
                70: 'siebzig',
                80: 'achtzig',
                90: 'neunzig',
                }
        self.dict_test(result)

    def test_toTenThousand(self):
        result = {
		100: 'einhundert',
		101: 'einhunderteins',
		102: 'einhundertzwei',
		110: 'einhundertzehn',
		153: 'einhundertdreiundfünfzig',
		200: 'zweihundert',
		201: 'zweihunderteins',
		202: 'zweihundertzwei',
		244: 'zweihundertvierundvierzig',
		300: 'dreihundert',
		400: 'vierhundert',
		500: 'fünfhundert',
		600: 'sechshundert',
		700: 'siebenhundert',
		800: 'achthundert',
		900: 'neunhundert',
		1000: 'eintausend',
		2000: 'zweitausend',
		2001: 'zweitausendeins',
		2011: 'zweitausendelf',
		3000: 'dreitausend',
		5000: 'fünftausend',
		6744: 'sechstausendsiebenhundertvierundvierzig',
                }
        self.dict_test(result)

    def test_years(self):
        result = {
                1998: 'neunzehnhundertachtundneunzig',
                1532: 'fünfzehnhundertzweiunddreißig',
                1494: 'vierzehnhundertvierundneunzig',
                1999: 'neunzehnhundertneunundneunzig',
                }
        self.dict_test(result)

    def test_largerNumbers(self):
        result = {
                14732512: 'vierzehnmillionensiebenhundertzweiunddreißigtausendfünfhundertzwölf'
                }
        self.dict_test(result)

    def test_helper(self):
        self.assertEqual(Number._get_some_powers(321444, 3), 321)

    def test_ordinals(self):
        result = {
                1: 'erste',
                2: 'zweite',
                9: 'neunte',
                10: 'zehnte',
                19: 'neunzehnte',
                20: 'zwanzigste',
                21: 'einundzwanzigste',
                100: 'einhundertste',
                1000: 'eintausendste',
                1944: 'neunzehnhundertvierundvierzigste',
                2144: 'zweitausendeinhundertvierundvierzigste',
                100000: 'einhunderttausendste',
                1000000: 'einemillionste',
                }
        self.dict_test(result, True)


if __name__ == '__main__':
    unittest.main()
