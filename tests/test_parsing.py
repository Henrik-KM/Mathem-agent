from mathem_agent.mathem import products_from_html, recipes_from_html


def test_products_from_next_data_html():
    html = '''
    <html><body><script id="__NEXT_DATA__" type="application/json">
    {"props":{"pageProps":{"dehydratedState":{"queries":[{"state":{"data":{"items":[
      {"type":"product","attributes":{"id":123,"name":"Pasta Girandole","nameExtra":"500 g","brand":"Barilla","grossPrice":16,"grossUnitPrice":32,"currency":"SEK","unitPriceQuantityAbbreviation":"kg","clientClassifiers":[{"name":"Prismatch"}],"promotions":[{"title":"2 för 25 kr"}]}}
    ]}}}]}}}}
    </script></body></html>
    '''
    products = products_from_html(html)
    assert len(products) == 1
    assert products[0].id == 123
    assert products[0].name == "Pasta Girandole"
    assert products[0].is_prismatch
    assert products[0].is_offer
    assert products[0].unit_price == 32


def test_recipes_from_html():
    html = '<a href="/se/recipes/123-krispig-lax">Krispig lax i krämig parmesansås</a>'
    recipes = recipes_from_html(html)
    assert recipes == [
        {
            "title": "Krispig lax i krämig parmesansås",
            "url": "https://www.mathem.se/se/recipes/123-krispig-lax",
        }
    ]
