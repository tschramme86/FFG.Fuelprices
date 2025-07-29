import azure.functions as func
from airium import Airium
import datetime
import pytz
import json
import logging
import pandas as pd
import re
import time

relevant_airports = [("EDVE", "Braunschweig"), 
                     ("EDCB", "Ballenstedt"), 
                     ("EDAD", "Dessau"),
                     ("ETND", "Diepholz"),
                     ("EDVM", "Hildesheim"),
                     ("EDVI", "Höxter"),
                     ("EDBM", "Magdeburg"),
                     ("EDVY", "Porta Westfalica"),
                     ("EDOV", "Stendal")]

class CachedItem(object):
    def __init__(self, key, value, duration=60):
        self.key = key
        self.value = value
        self.duration = duration
        self.timeStamp = time.time()
        self.expires_at = self.timeStamp + self.duration

    def __repr__(self):
        return '<CachedItem {%s:%s} expires at: %s>' % (self.key, self.value, self.expires_at)

class CachedDict(dict):
    def get(self, key, fn, duration):
        if key not in self \
            or self[key].expires_at < time.time():
                o = fn(key)
                self[key] = CachedItem(key, o, duration)

        return self[key].value

app = func.FunctionApp()
priceCache = CachedDict()

@app.route(route="api/prices/{icao}", auth_level=func.AuthLevel.ANONYMOUS)
def FuelPrices(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger "prices/icao" API function')
    icao = req.route_params.get('icao')

    if icao:
        prices = fuel_price.for_icao(icao)
        return func.HttpResponse(json.dumps(prices.as_json()), mimetype="application/json", status_code=200)
    else:
        return func.HttpResponse(
             "Calling this function requires a valid ICAO code in the URL path.",
             status_code=400
        )

@app.route(route="{ignored:maxlength(0)?}", auth_level=func.AuthLevel.ANONYMOUS)
def FuelPricesPage(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('Python HTTP trigger "pricepage" function')

    prices_page = FuelPricePage()
    for icao, name in relevant_airports:
        try:
            prices = fuel_price.for_icao(icao, name)
            prices_page.add_price(prices)
        except Exception as e:
            logging.error(f"Error fetching prices for {icao}: {e}")
    html_content = prices_page.create_page()
    return func.HttpResponse(html_content, mimetype="text/html", status_code=200)

class fuel_price:
    def __init__(self, icao, priceUl91, priceSuper, priceAvgas):
        self.icao = icao
        self.priceUl91 = priceUl91
        self.priceSuper = priceSuper
        self.priceAvgas = priceAvgas
        self.timeStamp = time.time()

    @staticmethod
    def for_icao(icao:  str, name: str = None):
        if icao is None or not isinstance(icao, str):
            raise ValueError("ICAO must be a valid string")
        
        fn = lambda icao: fuel_price.__for_icao_internal(icao, name)
        return priceCache.get(icao, fn, duration=60 * 60)

    def __for_icao_internal(icao: str, name: str = None):
        url = f'https://www.spritpreisliste.de/airports/{icao}'
        tables = pd.read_html(url) # Returns list of all tables on page
        info_table = tables[0] # Select table of interest
        # find row that starts with "100 LL Preis"
        priceAvgas = fuel_price.__parse_price(info_table[info_table.iloc[:, 0].str.startswith('100 LL Preis')].iloc[0][1])
        priceSuperPlus = fuel_price.__parse_price(info_table[info_table.iloc[:, 0].str.startswith('Super+ Preis')].iloc[0][1])
        priceUL91 = fuel_price.__parse_price(info_table[info_table.iloc[:, 0].str.startswith('UL91 Preis')].iloc[0][1])
        price_obj = fuel_price(icao, priceUL91, priceSuperPlus, priceAvgas)
        price_obj.name = name
        return price_obj

    @staticmethod
    def __parse_price(price_str):
        # Remove all non-numeric characters except for the decimal point
        price_str = re.sub(r'[^\d.,]', '', price_str[:4])
        # Replace comma with dot for decimal point
        price_str = price_str.replace(',', '.')
        return float(price_str) if price_str else None


    def get_non_avgas_prices(self):
        if self.priceSuper is not None:
            return self.priceSuper, "Super+"
        elif self.priceUl91 is not None:
            return self.priceUl91, "UL91"
        else:
            return None, None
    def get_avgas_price(self):
        if self.priceAvgas is not None:
            return self.priceAvgas, "Avgas"
        else:
            return None, None
    def as_json(self):
        avgas_price, avgas_type = self.get_avgas_price()
        non_avgas_price, fuel_type = self.get_non_avgas_prices()
        return {
            "icao": self.icao,
            "avgas_price": avgas_price,
            "non_avgas_price": non_avgas_price,
            "non_avgas_type": fuel_type
        }
    def __str__(self):
        avgas_price, avgas_type = self.get_avgas_price()
        non_avgas_price, fuel_type = self.get_non_avgas_prices()
        return f'{self.icao}: AvGas: {avgas_price:.2f} €/l, {fuel_type}: {non_avgas_price:.2f} €/l'

class FuelPricePage:
    def __init__(self):
        self.prices = []
    def add_price(self, price):
        if isinstance(price, fuel_price):
            self.prices.append(price)
        else:
            raise TypeError("Expected an instance of fuel_price")
    def create_page(self):
        """Creates an HTML page with the fuel prices."""

        # get top 3 avgas prices
        top3_avgas_prices = sorted(self.prices, key=lambda x: x.get_avgas_price()[0] if x.get_avgas_price()[0] is not None else float('inf'))[:3]
        top3_nonavgas_prices = sorted(self.prices, key=lambda x: x.get_non_avgas_prices()[0] if x.get_non_avgas_prices()[0] is not None else float('inf'))[:3]

        # newest timeStamp of all fuel prices
        newest_timestamp = max(price.timeStamp for price in self.prices) if self.prices else datetime.datetime.now().timestamp()

        a = Airium()
        a('<!DOCTYPE html>')
        with a.html(lang="de"):
            with a.head():
                a.meta(charset="utf-8")
                a.meta(name="viewport", content="width=device-width, initial-scale=1.0")
                a.title(_t="FFG | Günstig Tanken")
                a.link(rel="icon", sizes="32x32", href="https://www.ffg-braunschweig.de/wp-content/uploads/2021/07/cropped-FFG_Logo_Instagram_weiss-32x32.png")
                a.link(rel="icon", sizes="192x192", href="https://www.ffg-braunschweig.de/wp-content/uploads/2021/07/cropped-FFG_Logo_Instagram_weiss-192x192.png")
                a.link(rel="apple-touch-icon", href="https://www.ffg-braunschweig.de/wp-content/uploads/2021/07/cropped-FFG_Logo_Instagram_weiss-180x180.png")
                with a.style(type="text/css"):
                    a("""
                        body {
                            font-family: Arial, sans-serif;
                            margin: 0;
                            padding: 0;
                            background-color: #f0f0f0;
                            color: #333;
                        }
                        table {
                            width: 100%;
                            border-collapse: collapse;
                        }
                        th, td {
                            padding: 8px;
                            text-align: left;
                            border-bottom: 1px solid #ddd;
                        }
                        th {
                            background-color: #2c3e50;
                            color: white;
                        }
                        .top3price {
                            background-color: #e0f7fa;
                            font-weight: bold;
                        }
                    """)
            with a.body():
                a.img(src="https://www.ffg-braunschweig.de/wp-content/uploads/2019/07/ffg-logo_2_retina.png", style="float: left; width: 80px;")
                with a.h3():
                    a("Die FFG Flotte günstig tanken")
                with a.p():
                    a("Hier findest du die aktuellen Treibstoffpreise der Flugplätze, wo du mit Tankkarte oder auf Rechnung der FFG tanken kannst.")
                with a.table():
                    with a.thead():
                        with a.tr():
                            a.th(_t="ICAO")
                            a.th(_t="Name")
                            a.th(_t="Avgas")
                            a.th(_t="Super+ / UL91")
                    with a.tbody():
                        for price in self.prices:
                            with a.tr():
                                a.td(_t=price.icao)
                                a.td(_t=price.name if hasattr(price, 'name') else "N/A")
                                avgas_price, avgas_type = price.get_avgas_price()
                                if avgas_price is not None:
                                    if avgas_price <= top3_avgas_prices[-1].get_avgas_price()[0]:
                                        a.td(_t=f"{avgas_price:.2f} €/l", klass="top3price")
                                    else:
                                        a.td(_t=f"{avgas_price:.2f} €/l")
                                else:
                                    a.td(_t="N/A")

                                non_avgas_price, fuel_type = price.get_non_avgas_prices()
                                if non_avgas_price is not None:
                                    if non_avgas_price <= top3_nonavgas_prices[-1].get_non_avgas_prices()[0]:
                                        a.td(_t=f"{non_avgas_price:.2f} €/l ({fuel_type})", klass="top3price")
                                    else:
                                        a.td(_t=f"{non_avgas_price:.2f} €/l ({fuel_type})")
                                else:
                                    a.td(_t="N/A")
                with a.p():
                    a("Die Preise wurden von der Webseite")
                    with a.a(href="https://www.spritpreisliste.de/", _target="_blank", rel="noopener noreferrer"):
                        a("spritpreisliste.de")
                    a("abgerufen und können sich jederzeit ändern.")
                with a.p():
                    a("Letzter Datenabruf: ")
                    a(datetime.datetime.fromtimestamp(newest_timestamp, pytz.timezone("Europe/Berlin")).strftime('%Y-%m-%d %H:%M:%S'))
        return str(a)

