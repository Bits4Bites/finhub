from datetime import datetime
from zoneinfo import ZoneInfo

import country_converter as coco
import numpy as np
import pandas as pd
import yfinance as yf

from .. import config
from ..models import types

asx_index_yf_static_tickers = {
    "ASX20": "^ATLI",
    "ASX50": "^AFLI",
    "ASX100": "^ATOI",
    "ASX200": "^AXJO",
    "ASX300": "^AXKO",
    "ASX": "^AORD",  # ASX All Ordinaries
}

asx_sector_yf_static_tickers = {
    "ENERGY": "^AXEJ",
    "BASIC MATERIALS": "^AXMJ",
    "INDUSTRIALS": "^AXNJ",
    "CONSUMER CYCLICAL": "^AXDJ",  # S&P/ASX 200 Consumer Discretionary (Sector)
    "CONSUMER DEFENSIVE": "^AXSJ",  # S&P/ASX 200 Consumer Staples (Sector)
    "HEALTHCARE": "^AXHJ",
    "FINANCIAL SERVICES": "^AXFJ",  # S&P/ASX 200 Financials (Sector)
    "TECHNOLOGY": "^AXIJ",  # S&P/ASX 200 Information Technology (Sector)
    "COMMUNICATION SERVICES": "^AXTJ",
    "UTILITIES": "^AXUJ",
    "REAL ESTATE": "^AXRE",
}

us_index_yf_static_tickers = {
    "NASDAQ100": "^NDX",
    "NASDAQ": "^IXIC",  # NASDAQ Composite
    "SP500": "^SPX",  # ^GSPC
    "SP400": "^MID",  # SP400
    "SP600": "^SP600"
}

# us_main_yf_indices = [
#     "^DWCF",  # Dow Jones U.S. Total Stock Mark
#     "^IXIC",  # NASDAQ Composite
#     "^SPX",   # SP500
#     "^RUI",   # Russell 1000
# ]

us_sector_yf_static_tickers = {
    "ENERGY": "^SP500-1010",
    "BASIC MATERIALS": "^SP500-15",
    "INDUSTRIALS": "^SP500-20",
    "CONSUMER CYCLICAL": "^SP500-25",
    "CONSUMER DEFENSIVE": "^SP500-30",
    "HEALTHCARE": "^SP500-35",
    "FINANCIAL SERVICES": "^SP500-40",
    "TECHNOLOGY": "^SP500-45",
    "COMMUNICATION SERVICES": "^SP500-50",
    "UTILITIES": "^SP500-55",
    "REAL ESTATE": "^SP500-60",
}

us_industry_yf_static_tickers = {
    "ENERGY": {
        "OIL & GAS E&P": "^SP500-10102020",
        "OIL & GAS EQUIPMENT & SERVICES": "^SP500-10101020",
        "OIL & GAS INTEGRATED": "^SP500-10102010",
        "OIL & GAS MIDSTREAM": "^SP500-10102040",  # mapped to GICS sub-industry "Oil & Gas Storage & Transportation"
        "OIL & GAS REFINING & MARKETING": "^SP500-10102030",
        "OIL & GAS DRILLING": "^SP500-10101010",
        "THERMAL COAL": "^SP500-10102050",  # mapped to GICS sub-industry "Coal & Consumable Fuels"
        "URANIUM": "URA",  # No GICS sub-industry for Uranium, so using the Global X Uranium ETF as a proxy
    },
    "BASIC MATERIALS": {
        "COMMODITY CHEMICALS": "^SP500-15101010",
        "CHEMICALS": "^SP500-15101020",  # mapped to GICS sub-industry "Diversified Chemicals"
        "AGRICULTURAL INPUTS": "^SP500-15101030",  # mapped to GICS sub-industry "Fertilizers & Agricultural Chemicals"
        "INDUSTRIAL GASES": "^SP500-15101040",
        "SPECIALTY CHEMICALS": "^SP500-15101050",
        "BUILDING MATERIALS": "^SP500-15102010",  # mapped to GICS sub-industry "Construction Materials"
        "METAL, GLASS & PLASTIC CONTAINERS": "^SP500-15103010",
        "PAPER & PLASTIC PACKAGING PRODUCTS & MATERIALS": "^SP500-15103020",
        "ALUMINUM": "^SP500-15104010",
        "OTHER INDUSTRIAL METALS & MINING": "^SP500-15104020",  # mapped to GICS sub-industry "Diversified Metals & Mining"
        "COPPER": "^SP500-15104025",
        "GOLD": "^SP500-15104030",
        "OTHER PRECIOUS METALS & MINING": "^SP500-15104040",  # mapped to GICS sub-industry "Precious Metals & Minerals"
        "SILVER": "^SP500-15104045",
        "COKING COAL": "^SP500-15104050",  # mapped to GICS sub-industry "Steel"
        "STEEL": "^SP500-15104050",
        "LUMBER & WOOD PRODUCTION": "^SP500-15105010",  # mapped to GICS sub-industry "Forest Products"
        "PAPER & PAPER PRODUCTS": "^SP500-15105020",  # mapped to GICS sub-industry "Paper Products"
    },
    "INDUSTRIALS": {
        "AEROSPACE & DEFENSE": "^SP500-20101010",
        "BUILDING PRODUCTS & EQUIPMENT": "^SP500-20102010",  # mapped to GICS sub-industry "Building Products"
        "ENGINEERING & CONSTRUCTION": "^SP500-20103010",  # mapped to GICS sub-industry "Construction & Engineering"
        "ELECTRICAL EQUIPMENT & PARTS": "^SP500-20104010",  # mapped to GICS sub-industry "Electrical Components & Equipment"
        "HEAVY ELECTRICAL EQUIPMENT": "^SP500-20104020",
        "CONGLOMERATES": "^SP500-20105010",  # mapped to GICS sub-industry "Industrial Conglomerates"
        "CONSTRUCTION MACHINERY & HEAVY TRANSPORTATION EQUIPMENT": "^SP500-20106010",
        "FARM & HEAVY CONSTRUCTION MACHINERY": "^SP500-20106015", # mapped to GICS sub-industry "Agricultural & Farm Machinery"
        "TOOLS & ACCESSORIES": "^SP500-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "METAL FABRICATION": "^SP500-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "SPECIALTY INDUSTRIAL MACHINERY": "^SP500-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "INDUSTRIAL DISTRIBUTION": "^SP500-20107010",  # mapped to GICS sub-industry "Trading Companies & Distributors"
        "COMMERCIAL PRINTING": "^SP500-20201010",
        "POLLUTION & TREATMENT CONTROLS": "^SP500-20201050",  # mapped to GICS sub-industry "Environmental & Facilities Services"
        "WASTE MANAGEMENT": "^SP500-20201050",  # mapped to GICS sub-industry "Environmental & Facilities Services"
        "OFFICE SERVICES & SUPPLIES": "^SP500-20201060",
        "SPECIALTY BUSINESS SERVICES": "^SP500-20201070",  # mapped to GICS sub-industry "Diversified Support Services"
        "SECURITY & PROTECTION SERVICES": "^SP500-20201080",  # mapped to GICS sub-industry "Security & Alarm Services"
        "STAFFING & EMPLOYMENT SERVICES": "^SP500-20202010",  # mapped to GICS sub-industry "Human Resource & Employment Services"
        "CONSULTING SERVICES": "^SP500-20202020",  # mapped to GICS sub-industry "Research & Consulting Services"
        "DATA PROCESSING & OUTSOURCED SERVICES": "^SP500-20202030",
        "INTEGRATED FREIGHT & LOGISTICS": "^SP500-20301010",  # mapped to GICS sub-industry "Air Freight & Logistics"
        "AIRLINES": "^SP500-20302010",  # mapped to GICS sub-industry "Passenger Airlines"
        "MARINE SHIPPING": "^SP500-20303010",  # mapped to GICS sub-industry "Marine Transportation"
        "RAILROADS": "^SP500-20304010",  # mapped to GICS sub-industry "Rail Transportation"
        "TRUCKING": "^SP500-20304030",  # mapped to GICS sub-industry "Cargo Ground Transportation"
        "PASSENGER GROUND TRANSPORTATION": "^SP500-20304040",
        "AIRPORT SERVICES": "^SP500-20305010",
        "HIGHWAYS & RAILTRACKS": "^SP500-20305020",
        "MARINE PORTS & SERVICES": "^SP500-20305030",
        "RENTAL & LEASING SERVICES": "^SP500-202010",  # no exact GICS sub-industry mapping, map to industry "Commercial Services & Supplies"
    },
    "CONSUMER CYCLICAL": {
        "AUTO PARTS": "^SP500-25101010",  # mapped to GICS sub-industry "Automotive Parts & Equipment"
        "TIRES & RUBBER": "^SP500-25101020",
        "AUTO MANUFACTURERS": "^SP500-25102010",  # mapped to GICS sub-industry "Automobile Manufacturers"
        "MOTORCYCLE MANUFACTURERS": "^SP500-25102010",
        "CONSUMER ELECTRONICS": "^SP500-25201010",
        "FURNISHINGS, FIXTURES & APPLIANCES": "^SP500-25201020",  # mapped to GICS sub-industry "Home Furnishings"
        "RESIDENTIAL CONSTRUCTION": "^SP500-25201030",  # mapped to GICS sub-industry "HOMEBUILDING"
        "HOUSEHOLD APPLIANCES": "^SP500-25201040",
        "HOUSEWARES & SPECIALTIES": "^SP500-25201050",
        "RECREATIONAL VEHICLES": "^SP500-25202010",  # mapped to GICS sub-industry "Leisure Products"
        "LUXURY GOODS": "^SP500-25203010",  # mapped to GICS sub-industry "Apparel, Accessories & Luxury Goods"
        "APPAREL MANUFACTURING": "^SP500-25203010",  # mapped to GICS sub-industry "Apparel, Accessories & Luxury Goods"
        "FOOTWEAR & ACCESSORIES": "^SP500-25203020",  # mapped to GICS sub-industry "Footwear"
        "TEXTILE MANUFACTURING": "^SP500-25203030",  # mapped to GICS sub-industry "Textiles"
        "GAMBLING": "^SP500-25301010",  # mapped to GICS sub-industry "Casinos & Gaming"
        "RESORTS & CASINOS": "^SP500-25301010",  # mapped to GICS sub-industry "Casinos & Gaming"
        "LODGING": "^SP500-25301020",  # mapped to GICS sub-industry "Hotels, Resorts & Cruise Lines"
        "TRAVEL SERVICES": "^SP500-25301020",  # mapped to GICS sub-industry "Hotels, Resorts & Cruise Lines"
        "LEISURE": "^SP500-25301030",  # mapped to GICS sub-industry "Leisure Facilities"
        "RESTAURANTS": "^SP500-25301040",
        "EDUCATION SERVICES": "^SP500-25302010",
        "PERSONAL SERVICES": "^SP500-25302020",  # mapped to GICS sub-industry "Specialized Consumer Services"
        "DISTRIBUTORS": "^SP500-25501010",
        "DEPARTMENT STORES": "^SP500-25503030",  # mapped to GICS sub-industry "Broadline Retail"
        "INTERNET RETAIL": "^SP500-25503030",  # mapped to GICS sub-industry "Broadline Retail"
        "APPAREL RETAIL": "^SP500-25504010",
        "COMPUTER & ELECTRONICS RETAIL": "^SP500-25504020",
        "HOME IMPROVEMENT RETAIL": "^SP500-25504030",
        "SPECIALTY RETAIL": "^SP500-25504040",  # mapped to GICS sub-industry "Other Specialty Retail"
        "AUTO & TRUCK DEALERSHIPS": "^SP500-25504050",  # mapped to GICS sub-industry "Automotive Retail"
        "HOMEFURNISHING RETAIL": "^SP500-25504060",
        "PACKAGING & CONTAINERS": "^SP500-25201050",  # mapped to GICS sub-industry "Housewares & Specialties"
    },
    "CONSUMER DEFENSIVE": {
        "DRUG RETAIL": "^SP500-30101010",
        "FOOD DISTRIBUTION": "^SP500-30101020",  # mapped to GICS sub-industry "Food Distributors"
        "GROCERY STORES": "^SP500-30101030",  # mapped to GICS sub-industry "Food Retail"
        "DISCOUNT STORES": "^SP500-30101040",  # mapped to GICS sub-industry "Consumer Staples Merchandise Retail"
        "BEVERAGES - BREWERS": "^SP500-30201010",  # mapped to GICS sub-industry "Brewers"
        "DISTILLERS & VINTNERS": "^SP500-30201020",
        "BEVERAGES - NON-ALCOHOLIC": "^SP500-30201030",  # mapped to GICS sub-industry "Soft Drinks & Non-alcoholic Beverages"
        "FARM PRODUCTS": "^SP500-30202010",  # mapped to GICS sub-industry "Agricultural Products & Services"
        "CONFECTIONERS": "^SP500-30202030",  # mapped to GICS sub-industry "Packaged Foods & Meats"
        "PACKAGED FOODS": "^SP500-30202030",  # mapped to GICS sub-industry "Packaged Foods & Meats"
        "TOBACCO": "^SP500-30203010",
        "HOUSEHOLD & PERSONAL PRODUCTS": "^SP500-3030",  # mapped to GICS industry-group "Household & Personal Products"
        "EDUCATION & TRAINING SERVICES": "^SP500-25302010",  # mapped to GICS sub-industry "Education Services"
    },
    "HEALTHCARE": {
        "MEDICAL INSTRUMENTS & SUPPLIES": "^SP500-35101010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DEVICES": "^SP500-35101010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DISTRIBUTION": "^SP500-35102010",  # mapped to GICS sub-industry "Health Care Distributors"
        "HEALTH CARE SERVICES": "^SP500-35102015",
        "MEDICAL CARE FACILITIES": "^SP500-35102020",  # mapped to GICS sub-industry "Health Care Facilities"
        "HEALTHCARE PLANS": "^SP500-35102030",  # mapped to GICS sub-industry "Managed Health Care"
        "HEALTH INFORMATION SERVICES": "^SP500-35103010",  # mapped to GICS sub-industry "Health Care Technology"
        "BIOTECHNOLOGY": "^SP500-35201010",
        "DRUG MANUFACTURERS - GENERAL": "^SP500-35202010",  # mapped to GICS sub-industry "Pharmaceuticals"
        "DRUG MANUFACTURERS - SPECIALTY & GENERIC": "^SP500-35202010",  # mapped to GICS sub-industry "Pharmaceuticals"
        "DIAGNOSTICS & RESEARCH": "^SP500-35203010",  # mapped to GICS sub-industry "Life Sciences Tools & Services"
    },
    "FINANCIAL SERVICES": {
        "BANKS - DIVERSIFIED": "^SP500-40101010",  # mapped to GICS sub-industry "Diversified Banks"
        "BANKS - REGIONAL": "^SP500-40101015",  # mapped to GICS sub-industry "Regional Banks"
        "DIVERSIFIED FINANCIAL SERVICES": "^SP500-40201020",
        "FINANCIAL CONGLOMERATES": "^SP500-40201030",  # mapped to GICS sub-industry "Multi-sector Holdings"
        "SPECIALIZED FINANCE": "^SP500-40201040",
        "MORTGAGE FINANCE": "^SP500-40201050",  # mapped to GICS sub-industry "Commercial & Residential Mortgage Finance"
        "TRANSACTION & PAYMENT PROCESSING SERVICES": "^SP500-40201060",
        "CREDIT SERVICES": "^SP500-40202010",  # mapped to GICS sub-industry "Consumer Finance"
        "ASSET MANAGEMENT": "^SP500-40203010",  # mapped to GICS sub-industry "Asset Management & Custody Banks"
        # "INVESTMENT BANKING & BROKERAGE": "^SP500-40203020",
        "CAPITAL MARKETS": "^SP500-40203030",  # mapped to GICS sub-industry "Diversified Capital Markets"
        "FINANCIAL DATA & STOCK EXCHANGES": "^SP500-40203040",  # mapped to GICS sub-industry "Financial Exchanges & Data"
        "MORTGAGE REITS": "^SP500-40204010",
        "INSURANCE BROKERS": "^SP500-40301010",
        "INSURANCE - LIFE": "^SP500-40301020",  # mapped to GICS sub-industry "Life & Health Insurance"
        "INSURANCE - DIVERSIFIED": "^SP500-40301030",  # mapped to GICS sub-industry "Multi-line Insurance"
        "INSURANCE - SPECIALTY": "^SP500-40301040",  # mapped to GICS sub-industry "Property & Casualty Insurance"
        "INSURANCE - PROPERTY & CASUALTY": "^SP500-40301040",  # mapped to GICS sub-industry "Property & Casualty Insurance"
        "INSURANCE - REINSURANCE": "^SP500-40301050",  # mapped to GICS sub-industry "Reinsurance"
    },
    "TECHNOLOGY": {
        "INFORMATION TECHNOLOGY SERVICES": "^SP500-45102010",  # mapped to GICS sub-industry "IT Consulting & Other Services"
        "SOFTWARE - INFRASTRUCTURE": "^SP500-45102030",  # mapped to GICS sub-industry "Internet Services & Infrastructure"
        "SOFTWARE - APPLICATION": "^SP500-45103010",  # mapped to GICS sub-industry "Application Software"
        "SYSTEMS SOFTWARE": "^SP500-45103020",
        "COMMUNICATION EQUIPMENT": "^SP500-45201020",  # mapped to GICS sub-industry "Communications Equipment"
        "CONSUMER ELECTRONICS": "^SP500-45202030",  # mapped to GICS sub-industry "Technology Hardware, Storage & Peripherals"
        "COMPUTER HARDWARE": "^SP500-45202030",  # mapped to GICS sub-industry "Technology Hardware, Storage & Peripherals"
        "SCIENTIFIC & TECHNICAL INSTRUMENTS": "^SP500-45203010",  # mapped to GICS sub-industry "Electronic Equipment & Instruments"
        "SOLAR": "^SP500-45203015",  # mapped to GICS sub-industry "Electronic Components"
        "ELECTRONIC COMPONENTS": "^SP500-45203015",
        "ELECTRONIC MANUFACTURING SERVICES": "^SP500-45203020",
        "ELECTRONICS & COMPUTER DISTRIBUTION": "^SP500-45203030",  # mapped to GICS sub-industry "Technology Distributors"
        "SEMICONDUCTOR EQUIPMENT & MATERIALS": "^SP500-45301010",  # mapped to GICS sub-industry "Semiconductor Materials & Equipment"
        "SEMICONDUCTORS": "^SP500-45301020",
    },
    "COMMUNICATION SERVICES": {
        "ALTERNATIVE CARRIERS": "^SP500-50101010",
        "TELECOM SERVICES": "^SP500-5010",  # mapped to GICS industry group "Telecommunication Services"
        "ADVERTISING AGENCIES": "^SP500-50201010",  # mapped to GICS sub-industry "Advertising"
        "BROADCASTING": "^SP500-50201020",
        "CABLE & SATELLITE": "^SP500-50201030",
        "PUBLISHING": "^SP500-50201040",
        "ENTERTAINMENT": "^SP500-50202010",  # mapped to GICS sub-industry "Movies & Entertainment"
        "ELECTRONIC GAMING & MULTIMEDIA": "^SP500-50202020",  # mapped to GICS sub-industry "Interactive Home Entertainment"
        "INTERNET CONTENT & INFORMATION": "^SP500-50203010",  # mapped to GICS sub-industry "Interactive Media & Services"
    },
    "UTILITIES": {
        "UTILITIES - REGULATED ELECTRIC": "^SP500-55101010",  # mapped to GICS sub-industry "Electric Utilities"
        "UTILITIES - REGULATED GAS": "^SP500-55102010",  # mapped to GICS sub-industry "Gas Utilities"
        "UTILITIES - DIVERSIFIED": "^SP500-55103010",  # mapped to GICS sub-industry "Multi-Utilities"
        "UTILITIES - REGULATED WATER": "^SP500-55104010",  # mapped to GICS sub-industry "Water Utilities"
        "UTILITIES - INDEPENDENT POWER PRODUCERS": "^SP500-55105010",  # mapped to GICS sub-industry "Independent Power Producers & Energy Traders"
        "UTILITIES - RENEWABLE": "^SP500-55105020",  # mapped to GICS sub-industry "Renewable Electricity"
    },
    "REAL ESTATE": {
        "REIT - DIVERSIFIED": "^SP500-60101010",  # mapped to GICS sub-industry "Diversified REITs"
        "REIT - INDUSTRIAL": "^SP500-60102510",  # mapped to GICS sub-industry "Industrial REITs"
        "REIT - HOTEL & MOTEL": "^SP500-60103010",  # mapped to GICS sub-industry "Hotel & Resort REITs"
        "REIT - OFFICE": "^SP500-60104010",  # mapped to GICS sub-industry "Office REITs"
        "REIT - HEALTHCARE FACILITIES": "^SP500-60105010",  # mapped to GICS sub-industry "Health Care REITs"
        "REIT - RESIDENTIAL": "^SP500-60106010",  # mapped to GICS sub-industry "Multi-family Residential REITs"
        "SINGLE-FAMILY RESIDENTIAL REITS": "^SP500-60106020",
        "REIT - RETAIL": "^SP500-60107010",  # mapped to GICS sub-industry "Retail REITs"
        "REIT - SPECIALTY": "^SP500-60108010",  # mapped to GICS sub-industry "Other Specialized REITs"
        "SELF-STORAGE REITS": "^SP500-60108020",
        "TELECOM TOWER REITS": "^SP500-60108030",
        "TIMBER REITS": "^SP500-60108040",
        "DATA CENTER REITS": "^SP500-60108050",
        "REAL ESTATE - DIVERSIFIED": "^SP500-60201010",  # mapped to GICS sub-industry "Diversified Real Estate Activities"
        "REAL ESTATE OPERATING COMPANIES": "^SP500-60201020",
        "REAL ESTATE - DEVELOPMENT": "^SP500-60201030",  # mapped to GICS sub-industry "Real Estate Development"
        "REAL ESTATE SERVICES": "^SP500-60201040",
        "REIT - MORTGAGE": "^SP500-40204010",  # mapped to GICS sub-industry "Mortgage REITs" under Finance sector!
    },
}


def country_to_iso2(country: str) -> str:
    """
    Converts a country (name/code) to an ISO 3166-1 alpha-2 country code.

    Args:
        country (str): The country (name, code) to convert.

    Returns:
        str: The ISO 3166-1 alpha-2 country code.
    """
    return coco.convert(names=country, to="ISO2")


def normalize_exchange_code(exchange: str) -> str:
    """
    Normalize an exchange name to unified code (e.g. NYSE, NASDAQ...)
    """
    e = exchange.upper()
    return "NASDAQ" if "NASDAQ" in e else "NYSE" if "NY" in e else e


def lookup_market_yf_static_ticker(
    *,
    ticker: yf.Ticker = None,
    symbol: str = None,
) -> str | None:
    """
    Lookup a "market static ticker" (YF format) for a given stock.
    For example "market static ticker" for CBA.AX should be ASX20/ASX50, "market static ticker" for AAPL should be NASDAQ100.

    Args:
        ticker (yf.Ticker): The stock to look up market ticker for.
        symbol (str): The stock symbol to look up market ticker for.

    Returns:
        str: The market static ticker as a Yahoo Finance ticker.

    Remarks:
        Only supply either ticker or symbol. If both are supplied, tickr takes precedence.
    """
    if ticker is not None:
        symbol = to_exchange_ticker(ticker=ticker)
    else:
        symbol = to_exchange_ticker(symbol=symbol)
    exchange = symbol.split(":")[0]
    if exchange == "ASX":
        for index in asx_index_yf_static_tickers.keys():
            if is_in_index(symbol, index):
                return asx_index_yf_static_tickers[index]
        return asx_index_yf_static_tickers["ASX"]
    if exchange == "NASDAQ":
        return us_index_yf_static_tickers["NASDAQ100"] if is_in_index(symbol, "NASDAQ100") else us_index_yf_static_tickers["NASDAQ"]

    return None


def lookup_peer_yf_static_ticker(
    *,
    ticker: yf.Ticker = None,
    symbol: str = None,
    sector: str = None,
    industry: str = None,
) -> str | None:
    """
    Lookup a "market static ticker" (YF format) for a given stock.
    For example "market static ticker" for CBA.AX should be ASX20/ASX50, "market static ticker" for AAPL should be NASDAQ100.

    Args:
        ticker (yf.Ticker): The stock to look up market ticker for.
        symbol (str): The stock symbol to look up market ticker for.
        sector (str): The sector to look up market ticker for.
        industry (str, optional): The industry to filter for.

    Returns:
        str: The market static ticker as a Yahoo Finance ticker.

    Remarks:
        Only supply either ticker or symbol/sector/industry. If both are supplied, tickr takes precedence.
    """
    if ticker is not None:
        symbol = to_exchange_ticker(ticker=ticker)
        sector = ticker.info.get("sector")
        industry = ticker.info.get("industry")
    else:
        symbol = to_exchange_ticker(symbol=symbol)
    exchange = symbol.split(":")[0]
    sector = sector.upper() if sector is not None else None
    industry = industry.upper() if industry is not None else None
    if exchange == "ASX":
        if sector in asx_sector_yf_static_tickers:
            return asx_sector_yf_static_tickers[sector]
    if exchange == "NASDAQ" or exchange == "NYSE":
        if sector in us_industry_yf_static_tickers and industry in us_industry_yf_static_tickers[sector]:
            return us_industry_yf_static_tickers[sector][industry]
        if sector in us_sector_yf_static_tickers:
            return us_sector_yf_static_tickers[sector]

    return None


def number_to_human_format(num: int | float, precision: int = 2):
    """
    Convert a number into a human-readable format with K, M, B, T suffixes.

    Args:
        num (int|float): The number to format.
        precision (int): Decimal places to keep.

    Returns:
        str: Formatted string.
    """
    # Handle negative numbers
    sign = "-" if num < 0 else ""
    num = abs(num)

    # Define suffixes
    suffixes = ["", "K", "M", "B", "T"]
    idx = 0

    # Scale down the number
    while num >= 1000 and idx < len(suffixes) - 1:
        num /= 1000.0
        idx += 1

    # Format with given precision
    formatted = f"{num:.{precision}f}".rstrip("0").rstrip(".")
    return f"{sign}{formatted}{suffixes[idx]}"


def tz_from_yf_ticker(yf_ticker: str) -> ZoneInfo:
    """
    Gets the timezone for a Yahoo Finance ticker.

    Args:
        yf_ticker (str): The ticker for the Yahoo Finance ticker (e.g. CBA.AX or APPL).

    Returns:
        ZoneInfo: The timezone for the Yahoo Finance ticker, default is America/New_York
    """
    yf_ticker = yf_ticker.upper()
    if yf_ticker.endswith(".AX"):
        return ZoneInfo("Australia/Sydney")
    elif yf_ticker.endswith(".VN"):
        return ZoneInfo("Asia/Ho_Chi_Minh")
    else:
        return ZoneInfo("America/New_York")


def country_code_from_yf_ticker(yf_ticker: str) -> str:
    """
    Gets the country code for a Yahoo Finance ticker.

    Args:
        yf_ticker (str): The ticker for the Yahoo Finance ticker (e.g. CBA.AX or APPL).

    Returns:
        str: The country code for the Yahoo Finance ticker, default is US
    """
    yf_ticker = yf_ticker.upper()
    if yf_ticker.endswith(".AX"):
        return "AU"
    elif yf_ticker.endswith(".VN"):
        return "VN"
    else:
        return "US"


def yyyy_mm_dd_to_iso(yyyy_mm_dd: str, tz: ZoneInfo = None, tz_name: str = None) -> str | None:
    """
    Converts a date string in the format 'YYYY-MM-DD' to ISO format 'YYYY-MM-DD 00:00:00+hh:mm'.

    Args:
        yyyy_mm_dd (str): The date in the format YYYY-MM-DD
        tz (ZoneInfo, optional): The timezone to use. Defaults to None.
        tz_name (str, optional): The timezone to use. Defaults to None.

    Returns:
        str: The date in ISO format, or None if the input date string is invalid.

    Remarks:
        If both tz and tz_name are provided, tz will be used.
    """
    tz = tz or (ZoneInfo(tz_name) if tz_name else ZoneInfo("UTC"))
    try:
        return datetime.strptime(yyyy_mm_dd, "%Y-%m-%d").replace(tzinfo=tz).isoformat(sep=" ", timespec="seconds")
    except ValueError:
        return None


def to_exchange_ticker(*, ticker: yf.Ticker = None, symbol: str = None) -> str | None:
    """
    Converts a stock symbol to EXCHANGE:CODE format
    - If symbol is already in format EXCHANGE:CODE, it is returned as is.
    - If symbol is in YF format (e.g., "AAPL", "CBA.AX" or "BID.VN"), try best to convert to EXCHANGE:CODE.
    - Otherwise, return symbol as is.

    Args:
        ticker (yf.Ticker, optional): The ticker to convert to EXCHANGE:CODE.
        symbol (str): The stock symbol to convert to EXCHANGE:CODE format.

    Returns:
        str: The stock symbol as EXCHANGE:CODE.

    Remarks:
        Supply either ticker or symbol. If both are supplied, ticker takes precedence.
    """
    if ticker is None and symbol is None:
        return None

    if ticker is None and ":" in symbol:
        return symbol.upper()

    ticker = yf.Ticker(symbol) if ticker is None else ticker
    exchange = normalize_exchange_code(ticker.info.get("fullExchangeName", ticker.info.get("exchange", "")))
    symbol = ticker.info.get("symbol")
    if symbol.endswith(".VN") or symbol.endswith(".AX"):
        return f"{exchange}:{symbol[:-3]}"
    else:
        return f"{exchange}:{symbol}"


def to_yf_ticker(symbol: str) -> str:
    """
    Converts a stock symbol to a Yahoo Finance ticker format.
    - If symbol is already in YF format (e.g., "AAPL", "CBA.AX" or "BID.VN"), return as is.
    - If symbol is in format EXCHANGE:CODE (e.g., "ASX:CBA", "HOSE:BID"), convert to YF format (e.g., "CBA.AX", "BID.VN").
    - Otherwise, return symbol as is.

    Args:
        symbol (str): The stock symbol to convert to YF ticker format.

    Returns:
        str: The stock symbol as a Yahoo Finance ticker.
    """
    symbol = symbol.upper()
    if ":" in symbol:
        exchange, ticker = symbol.split(":", 1)
        if exchange == "ASX":
            return f"{ticker}.AX"
        elif exchange == "HOSE" or exchange == "HNX" or exchange == "UPCOM":
            return f"{ticker}.VN"
        elif exchange == "NYSE" or exchange == "NASDAQ":
            return ticker
    return symbol


def is_in_index(symbol: str, index: str) -> bool:
    """
    Checks if a stock symbol in a market index.

    Args:
        symbol (str): The stock symbol to check, should be in format EXCHANGE:CODE.
        index (str): The market index.

    Returns:
        bool: True if the stock symbol in a market index, False otherwise.
    """
    index = index.upper()
    if index in config.market_indices.indices:
        symbol = to_exchange_ticker(symbol=symbol)
        return symbol in config.market_indices.indices[index]
    return False


def classify_market_cap(
    ticker: yf.Ticker = None, /, country: str = None, exchange_symbol: str = None, market_cap: int = None
) -> tuple[types.MarketCapType | None, str | None]:
    """
    Classifies a stock market cap.

    Args:
        ticker (yf.Ticker): The stock ticker to classify.
        country (str): The country to classify (ISO2 country code).
        exchange_symbol (str): The exchange ticker to classify (format EXCHANGE:CODE).
        market_cap (int): The market cap to classify.

    Returns:
        tuple[models.MarketCapType|None, str|None]: classified market cap and optional index

    Remarks:
        Supply either ticker or tuple[country, exchange_ticker, market_cap]. If both are supplied, ticker will be used.
    """
    cap_size: types.MarketCapType = None
    market_index = None
    if ticker is not None:
        country = country_to_iso2(ticker.info.get("country", ticker.info.get("region", "US")))
        exchange = normalize_exchange_code(ticker.info.get("fullExchangeName"))
        symbol = ticker.info.get("symbol").upper().split(".")[0]
        exchange_symbol = f"{exchange}:{symbol}"
        market_cap = int(ticker.info.get("marketCap")) if ticker.info.get("marketCap") is not None else 0

    if country == "AU" or country == "US":
        if market_cap >= 10_000_000_000:
            cap_size = types.LARGE_CAP
        elif market_cap >= 2_000_000_000:
            cap_size = types.MID_CAP
        elif market_cap >= 300_000_000:
            cap_size = types.SMALL_CAP
        elif market_cap >= 50_000_000:
            cap_size = types.MICRO_CAP
        else:
            cap_size = types.NANO_CAP

        for index in ["ASX50", "NASDAQ100", "SP500"]:
            # if listed in any of these index, definitely Large
            if is_in_index(exchange_symbol, index):
                market_index = index
                cap_size = types.LARGE_CAP
                break
        if is_in_index(exchange_symbol, "SP400"):
            market_index = "SP400"
            cap_size = types.MID_CAP
        if is_in_index(exchange_symbol, "SP600"):
            market_index = "SP600"
            cap_size = types.SMALL_CAP

        if market_index is None:
            if is_in_index(exchange_symbol, "ASX100"):
                # if in ASX100, move up 1 tier (mid -> large, small -> mid)
                market_index = "ASX100"
                if cap_size == types.MID_CAP:
                    cap_size = types.LARGE_CAP
                elif cap_size == types.SMALL_CAP:
                    cap_size = types.MID_CAP
            elif not is_in_index(exchange_symbol, "ASX300"):
                # if outside ASX300, move down 1 tier (mid -> small, small -> micro)
                if cap_size == types.SMALL_CAP:
                    cap_size = types.MICRO_CAP
                elif cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP

        if market_index is None:
            for index in ["ASX50", "ASX100", "ASX200", "ASX300"]:
                if is_in_index(exchange_symbol, index):
                    market_index = index
                    break

    if country == "VN":
        if market_cap >= 10_000_000_000_000:
            cap_size = types.LARGE_CAP
        elif market_cap >= 1_000_000_000_000:
            cap_size = types.MID_CAP
        elif market_cap >= 100_000_000_000:
            cap_size = types.SMALL_CAP
        elif market_cap >= 10_000_000_000:
            cap_size = types.MICRO_CAP
        else:
            cap_size = types.NANO_CAP

        if exchange_symbol.startswith("HOSE:"):
            if is_in_index(exchange_symbol, "VN30"):
                # in VN30 --> Large
                market_index = "VN30"
                cap_size = types.LARGE_CAP
            elif is_in_index(exchange_symbol, "VN100"):
                # in VN100 --> Mid
                market_index = "VN100"
                cap_size = types.MID_CAP
            else:
                # down 1 level
                if cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP
                elif cap_size == types.LARGE_CAP:
                    cap_size = types.MID_CAP

        if exchange_symbol.startswith("HNX:"):
            if is_in_index(exchange_symbol, "HNX30"):
                market_index = "HN30"
                if cap_size == types.SMALL_CAP:
                    cap_size = types.MID_CAP
            else:
                # down 1 level
                if cap_size == types.MID_CAP:
                    cap_size = types.SMALL_CAP
                elif cap_size == types.LARGE_CAP:
                    cap_size = types.MID_CAP

    return cap_size, market_index


def calc_rsi(data: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """
    Calculates the Relative Strength Index (RSI) for a given DataFrame of stock prices.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        period (int, optional): The number of periods to use for the RSI calculation. Defaults to 14.

    Returns:
        DataFrame: A DataFrame containing the RSI values, with the same index as the input data.
    """
    delta = data["Close"].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def calc_trend_sma(data: pd.DataFrame, short: int = 50, long: int = 100) -> float:
    """
    Calculates the trend over the period of the data using SMA comparison method.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        short (int, optional): The number of periods to use for the SMA calculation. Defaults to 50.
        long (int, optional): The number of periods to use for the SMA calculation. Defaults to 100.

    Returns:
        float: The trend over the period of the stock prices (MA-short - MA-long) / MA-long
    """
    if len(data) < long or len(data) < short:
        return 0
    sma_short = data["Close"].rolling(window=short).mean()
    sma_long = data["Close"].rolling(window=long).mean()
    result = float((sma_short.iloc[-1] - sma_long.iloc[-1]) / sma_long.iloc[-1])
    return result


def calc_trend_ema(data: pd.DataFrame, short: int = 21, long: int = 55) -> float:
    """
    Calculates the trend over the period of the data using EMA comparison method.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with a 'Close' column.
        short (int, optional): The number of periods to use for the SMA calculation. Defaults to 21.
        long (int, optional): The number of periods to use for the SMA calculation. Defaults to 55.

    Returns:
        float: The trend over the period of the stock prices (MA-short - MA-long) / MA-long
    """
    if len(data) < long or len(data) < short:
        return 0
    ema_short = data["Close"].ewm(span=short).mean()
    ema_long = data["Close"].ewm(span=long).mean()
    result = float((ema_short.iloc[-1] - ema_long.iloc[-1]) / ema_long.iloc[-1])
    return result


def find_volume_spikes(data: pd.DataFrame, threshold_multiplier: float = 2.5) -> pd.DataFrame:
    """
    Identifies volume spikes in the stock data.
    A volume spike is defined as a day when the trading volume is greater than the average volume over the period multiplied by the threshold_multiplier.
    """
    avg_volume = data["Volume"].mean()
    threshold = avg_volume * threshold_multiplier
    spikes = data[data["Volume"] >= threshold]
    return spikes


def analyze_past_dividends(data: pd.DataFrame, recovery_days_threshold: int = 28) -> pd.DataFrame:
    """
    Analyzes the past dividends over the period of the stock data.

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with 'Close' and 'Dividends' column.
        recovery_days_threshold (int, optional): The number of days to look for price recovery after the ex-dividend date. Defaults to 28.

    Returns:
        DataFrame: A DataFrame containing the dividend analysis, with the same index as the input data, containing columns for dividend analysis
    """
    # Algorithm:
    # - Ex-Div date is the date where fields Dividends > 0
    # - For each Ex-Div date:
    #   - Get value of Close field of the previous date (PreExDivPrice)
    #   - For the next recovery_days_threshold days, check for the first date where Close price >= PreExDivPrice, or None if not found
    dividend_data = data[data["Dividends"] > 0].copy()
    if dividend_data.empty:
        return dividend_data
    if recovery_days_threshold < 1:
        recovery_days_threshold = 10

    dividend_data["DVT"] = (
        (dividend_data["Open"] + dividend_data["Close"] + dividend_data["High"] + dividend_data["Low"])
        / 4
        * dividend_data["Volume"]
    )
    dividend_data = dividend_data[["Dividends", "Open", "Close", "Volume", "DVT"]]
    dividend_data["PreExDivPrice"] = data["Close"].shift(1)
    # for t in [1,3,5,10,20,30]:
    #     dividend_data[f"DRE{t}"] = (data["Close"].shift(-t)-dividend_data["PreExDivPrice"]) / (dividend_data["Dividends"]*sqrt(t))

    # dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["Open"]  # drop amount
    # # set to 0 if Drop < 0
    # # dividend_data["Drop"] = dividend_data["Drop"].apply(lambda x: x if x > 0 else 0)
    # dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    dividend_data["RecoveryDays"] = None
    dividend_data["PostExDivPeak"] = None
    dividend_data["PostExDivFloor"] = None
    for idx in dividend_data.index:
        pre_ex_div_price = dividend_data.at[idx, "PreExDivPrice"]
        for i in range(1, recovery_days_threshold + 1):
            if idx + pd.Timedelta(days=i) in data.index:
                close_price = data.at[idx + pd.Timedelta(days=i), "Close"]
                if (
                    dividend_data.at[idx, "PostExDivPeak"] is None
                    or close_price > dividend_data.at[idx, "PostExDivPeak"]
                ):
                    # peak price can continue after recovery
                    dividend_data.at[idx, "PostExDivPeak"] = close_price
                if dividend_data.at[idx, "PostExDivFloor"] is None or (
                    close_price < dividend_data.at[idx, "PostExDivFloor"]
                    and dividend_data.at[idx, "RecoveryDays"] is None
                ):
                    # only set floor price if not recovered yet
                    dividend_data.at[idx, "PostExDivFloor"] = close_price
                if (
                    close_price >= pre_ex_div_price
                    and dividend_data.at[idx, "Volume"] > 0
                    and dividend_data.at[idx, "RecoveryDays"] is None
                ):
                    # recovery day is the first day close_price >= pre_ex_div_price and has transacted volume
                    dividend_data.at[idx, "RecoveryDays"] = i

    # price might drop a few days later, not exactly on the ex-div day
    dividend_data["Drop"] = dividend_data["PreExDivPrice"] - dividend_data["PostExDivFloor"]
    dividend_data["DropRatio"] = dividend_data["Drop"] / dividend_data["Dividends"]

    return dividend_data


def calc_bid_ask_spread_roll(data: pd.DataFrame) -> float | None:
    """
    Calculates the bid/ask spread over the period of the stock data, using Roll’s Estimator

    Args:
        data (DataFrame): The DataFrame of stock prices (obtained from yfinance) with 'Close' column.

    Returns:
        float: The bid/ask spread over the period of the stock data, calculated using Roll’s Estimator
    """
    if len(data) < 2:
        return None
    data = data.copy()
    data["Price_Change"] = data["Close"].diff()
    data["Prev_Price_Change"] = data["Price_Change"].shift(1)

    # Calculate covariance between today's change and yesterday's change
    cov = data["Price_Change"].cov(data["Prev_Price_Change"])

    if cov < 0:
        # Roll's formula
        estimated_spread_dollar = 2 * np.sqrt(-cov)
        latest_close = data["Close"].iloc[-1]
        estimated_spread = estimated_spread_dollar / latest_close
        return float(estimated_spread)

    # Roll's Estimator failed (Covariance is positive). Stock is trending too hard.
    return None
