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
    "SP500": "^GSPC",
    "SP400": "^SP400",
    "SP600": "^SP600",
    "RUSSELL1000": "^RUI",
    "RUSSELL2000": "^RUT",
    "DOWJONES": "^DWCF",  # Dow Jones U.S. Total Stock Mark
}

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
        "OIL & GAS E&P": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "OIL & GAS EQUIPMENT & SERVICES": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "OIL & GAS INTEGRATED": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "OIL & GAS MIDSTREAM": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "OIL & GAS REFINING & MARKETING": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "OIL & GAS DRILLING": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "THERMAL COAL": "^SP500-101020",  # mapped to GICS industry "Oil, Gas & Consumable Fuels"
        "URANIUM": "URA",  # No GICS sub-industry for Uranium, so using the Global X Uranium ETF as a proxy
    },
    "BASIC MATERIALS": {
        "COMMODITY CHEMICALS": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "CHEMICALS": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "AGRICULTURAL INPUTS": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "INDUSTRIAL GASES": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "SPECIALTY CHEMICALS": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "BUILDING MATERIALS": "^SP500-151020",  # mapped to GICS industry "Construction Materials"
        "METAL, GLASS & PLASTIC CONTAINERS": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "PAPER & PLASTIC PACKAGING PRODUCTS & MATERIALS": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "ALUMINUM": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "OTHER INDUSTRIAL METALS & MINING": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "COPPER": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "GOLD": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "OTHER PRECIOUS METALS & MINING": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "SILVER": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "COKING COAL": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "STEEL": "^SP500-151040",  # mapped to GICS industry "Metals & Mining"
        "LUMBER & WOOD PRODUCTION": "^SP500-1510",  # mapped to GICS industry group "Materials"
        "PAPER & PAPER PRODUCTS": "^SP500-1510",  # mapped to GICS industry group "Materials"
    },
    "INDUSTRIALS": {
        "AEROSPACE & DEFENSE": "^SP500-201010",  # mapped to GICS industry "Aerospace & Defense"
        "BUILDING PRODUCTS & EQUIPMENT": "^SP500-201020",  # mapped to GICS industry "Building Products"
        "ENGINEERING & CONSTRUCTION": "^SP500-201030",  # mapped to GICS industry "Construction & Engineering"
        "ELECTRICAL EQUIPMENT & PARTS": "^SP500-201040",  # mapped to GICS industry "Electrical Equipment"
        "HEAVY ELECTRICAL EQUIPMENT": "^SP500-201040",  # mapped to GICS industry "Electrical Equipment"
        "CONGLOMERATES": "^SP500-201050",  # mapped to GICS industry "Industrial Conglomerates"
        "CONSTRUCTION MACHINERY & HEAVY TRANSPORTATION EQUIPMENT": "^SP500-201060",  # mapped to GICS industry "Machinery"
        "FARM & HEAVY CONSTRUCTION MACHINERY": "^SP500-201060",  # mapped to GICS industry "Machinery"
        "TOOLS & ACCESSORIES": "^SP500-201060",  # mapped to GICS industry "Machinery"
        "METAL FABRICATION": "^SP500-201060",  # mapped to GICS industry "Machinery"
        "SPECIALTY INDUSTRIAL MACHINERY": "^SP500-201060",  # mapped to GICS industry "Machinery"
        "INDUSTRIAL DISTRIBUTION": "^SP500-201070",  # mapped to GICS industry "Trading Companies & Distributors"
        "COMMERCIAL PRINTING": "^SP500-202010",  # mapped to GICS industry "Commercial Services & Supplies"
        "POLLUTION & TREATMENT CONTROLS": "^SP500-202010",  # mapped to GICS industry "Commercial Services & Supplies"
        "WASTE MANAGEMENT": "^SP500-202010",  # mapped to GICS industry "Commercial Services & Supplies"
        "OFFICE SERVICES & SUPPLIES": "^SP500-202010",  # mapped to GICS industry "Commercial Services & Supplies"
        "SPECIALTY BUSINESS SERVICES": "^SP500-202010",  # mapped to GICS industry "Commercial Services & Supplies"
        "SECURITY & PROTECTION SERVICES": "^SP500-202010",  # mapped to GICS industry "Commercial Services & Supplies"
        "STAFFING & EMPLOYMENT SERVICES": "^SP500-2020",  # mapped to GICS industry group "Commercial & Professional Services"
        "CONSULTING SERVICES": "^SP500-2020",  # mapped to GICS industry group "Commercial & Professional Services"
        "DATA PROCESSING & OUTSOURCED SERVICES": "^SP500-2020",  # mapped to GICS industry group "Commercial & Professional Services"
        "INTEGRATED FREIGHT & LOGISTICS": "^SP500-203010",  # mapped to GICS industry "Air Freight & Logistics"
        "AIRLINES": "^SP500-203020",  # mapped to GICS industry "Passenger Airlines"
        "MARINE SHIPPING": "^SP500-2030",  # mapped to GICS industry group "Transportation"
        "RAILROADS": "^SP500-203040",  # mapped to GICS industry "Ground Transportation"
        "TRUCKING": "^SP500-203040",  # mapped to GICS industry "Ground Transportation"
        "PASSENGER GROUND TRANSPORTATION": "^SP500-203040",  # mapped to GICS industry "Ground Transportation"
        "AIRPORT SERVICES": "^SP500-2030",  # mapped to GICS industry group "Transportation"
        "HIGHWAYS & RAILTRACKS": "^SP500-2030",  # mapped to GICS industry group "Transportation"
        "MARINE PORTS & SERVICES": "^SP500-2030",  # mapped to GICS industry group "Transportation"
        "RENTAL & LEASING SERVICES": "^SP500-202010",  # no exact GICS sub-industry mapping, map to industry "Commercial Services & Supplies"
    },
    "CONSUMER CYCLICAL": {
        "AUTO PARTS": "^SP500-251010",  # mapped to GICS industry "Automobile Components"
        "TIRES & RUBBER": "^SP500-251010",  # mapped to GICS industry "Automobile Components"
        "AUTO MANUFACTURERS": "^SP500-251020",  # mapped to GICS industry "Automobiles"
        "MOTORCYCLE MANUFACTURERS": "^SP500-251020",  # mapped to GICS industry "Automobiles"
        "CONSUMER ELECTRONICS": "^SP500-252010",  # mapped to GICS industry "Household Durables"
        "FURNISHINGS, FIXTURES & APPLIANCES": "^SP500-252010",  # mapped to GICS industry "Household Durables"
        "RESIDENTIAL CONSTRUCTION": "^SP500-252010",  # mapped to GICS industry "Household Durables"
        "HOUSEHOLD APPLIANCES": "^SP500-252010",  # mapped to GICS industry "Household Durables"
        "HOUSEWARES & SPECIALTIES": "^SP500-252010",  # mapped to GICS industry "Household Durables"
        "PACKAGING & CONTAINERS": "^SP500-252010",  # mapped to GICS industry "Household Durables"
        "RECREATIONAL VEHICLES": "^SP500-252020",  # mapped to GICS industry "Leisure Products"
        "LUXURY GOODS": "^SP500-252030",  # mapped to GICS industry "Textiles, Apparel & Luxury Goods"
        "APPAREL MANUFACTURING": "^SP500-252030",  # mapped to GICS industry "Textiles, Apparel & Luxury Goods"
        "FOOTWEAR & ACCESSORIES": "^SP500-252030",  # mapped to GICS industry "Textiles, Apparel & Luxury Goods"
        "TEXTILE MANUFACTURING": "^SP500-252030",  # mapped to GICS industry "Textiles, Apparel & Luxury Goods"
        "GAMBLING": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "RESORTS & CASINOS": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "LODGING": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "TRAVEL SERVICES": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "LEISURE": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "RESTAURANTS": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "EDUCATION SERVICES": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "PERSONAL SERVICES": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
        "DISTRIBUTORS": "^SP500-255010",  # mapped to GICS industry "Distributors"
        "DEPARTMENT STORES": "^SP500-2550",  # mapped to GICS industry group "Consumer Discretionary Distribution & Retail"
        "INTERNET RETAIL": "^SP500-2550",  # mapped to GICS industry group "Consumer Discretionary Distribution & Retail"
        "APPAREL RETAIL": "^SP500-255040",  # mapped to GICS industry "Specialty Retail"
        "COMPUTER & ELECTRONICS RETAIL": "^SP500-255040",  # mapped to GICS industry "Specialty Retail"
        "HOME IMPROVEMENT RETAIL": "^SP500-255040",  # mapped to GICS industry "Specialty Retail"
        "SPECIALTY RETAIL": "^SP500-255040",  # mapped to GICS industry "Specialty Retail"
        "AUTO & TRUCK DEALERSHIPS": "^SP500-255040",  # mapped to GICS industry "Specialty Retail"
        "HOMEFURNISHING RETAIL": "^SP500-255040",  # mapped to GICS industry "Specialty Retail"
    },
    "CONSUMER DEFENSIVE": {
        "DRUG RETAIL": "^SP500-3010",  # mapped to GICS industry group "Consumer Staples Distribution & Retail"
        "FOOD DISTRIBUTION": "^SP500-3010",  # mapped to GICS industry group "Consumer Staples Distribution & Retail"
        "GROCERY STORES": "^SP500-3010",  # mapped to GICS industry group "Consumer Staples Distribution & Retail"
        "DISCOUNT STORES": "^SP500-3010",  # mapped to GICS industry group "Consumer Staples Distribution & Retail"
        "BEVERAGES - BREWERS": "^SP500-302010",  # mapped to GICS industry "Beverages"
        "DISTILLERS & VINTNERS": "^SP500-302010",  # mapped to GICS industry "Beverages"
        "BEVERAGES - NON-ALCOHOLIC": "^SP500-302010",  # mapped to GICS industry "Beverages"
        "FARM PRODUCTS": "^SP500-302020",  # mapped to GICS industry "Food Products"
        "CONFECTIONERS": "^SP500-302020",  # mapped to GICS industry "Food Products"
        "PACKAGED FOODS": "^SP500-302020",  # mapped to GICS industry "Food Products"
        "TOBACCO": "^SP500-302030",  # mapped to GICS industry "Tobacco"
        "HOUSEHOLD & PERSONAL PRODUCTS": "^SP500-3030",  # mapped to GICS industry-group "Household & Personal Products"
        "EDUCATION & TRAINING SERVICES": "^SP500-2530",  # mapped to GICS industry group "Consumer Services"
    },
    "HEALTHCARE": {
        "MEDICAL INSTRUMENTS & SUPPLIES": "^SP500-351010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DEVICES": "^SP500-351010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DISTRIBUTION": "^SP500-351020",  # mapped to GICS industry "Health Care Providers & Services"
        "HEALTH CARE SERVICES": "^SP500-351020",  # mapped to GICS industry "Health Care Providers & Services"
        "MEDICAL CARE FACILITIES": "^SP500-351020",  # mapped to GICS industry "Health Care Providers & Services"
        "HEALTHCARE PLANS": "^SP500-351020",  # mapped to GICS industry "Health Care Providers & Services"
        "HEALTH INFORMATION SERVICES": "^SP500-3510",  # mapped to GICS industry group "Health Care Equipment & Services"
        "BIOTECHNOLOGY": "^SP500-352010",  # mapped to GICS industry "Biotechnology"
        "DRUG MANUFACTURERS - GENERAL": "^SP500-352020",  # mapped to GICS industry "Pharmaceuticals"
        "DRUG MANUFACTURERS - SPECIALTY & GENERIC": "^SP500-352020",  # mapped to GICS industry "Pharmaceuticals"
        "DIAGNOSTICS & RESEARCH": "^SP500-3520",  # mapped to GICS industry group "Pharmaceuticals, Biotechnology & Life Sciences"
    },
    "FINANCIAL SERVICES": {
        "BANKS - DIVERSIFIED": "^SP500-4010",  # mapped to GICS industry group "Banks"
        "BANKS - REGIONAL": "^SP500-4010",  # mapped to GICS industry group "Banks"
        "DIVERSIFIED FINANCIAL SERVICES": "^SP500-402010",  # mapped to GICS industry "Financial Services"
        "FINANCIAL CONGLOMERATES": "^SP500-402010",  # mapped to GICS industry "Financial Services"
        "SPECIALIZED FINANCE": "^SP500-402010",  # mapped to GICS industry "Financial Services"
        "MORTGAGE FINANCE": "^SP500-402010",  # mapped to GICS industry "Financial Services"
        "TRANSACTION & PAYMENT PROCESSING SERVICES": "^SP500-402010",  # mapped to GICS industry "Financial Services"
        "CREDIT SERVICES": "^SP500-402020",  # mapped to GICS industry "Consumer Finance"
        "ASSET MANAGEMENT": "^SP500-402030",  # mapped to GICS industry "Capital Markets"
        "CAPITAL MARKETS": "^SP500-402030",  # mapped to GICS industry "Capital Markets"
        "FINANCIAL DATA & STOCK EXCHANGES": "^SP500-402030",  # mapped to GICS industry "Capital Markets"
        "MORTGAGE REITS": "^SP500-4020",  # mapped to GICS industry group "Financial Services"
        "INSURANCE BROKERS": "^SP500-4030",  # mapped to GICS industry group "Insurance"
        "INSURANCE - LIFE": "^SP500-4030",  # mapped to GICS industry group "Insurance"
        "INSURANCE - DIVERSIFIED": "^SP500-4030",  # mapped to GICS industry group "Insurance"
        "INSURANCE - SPECIALTY": "^SP500-4030",  # mapped to GICS industry group "Insurance"
        "INSURANCE - PROPERTY & CASUALTY": "^SP500-4030",  # mapped to GICS industry group "Insurance"
        "INSURANCE - REINSURANCE": "^SP500-4030",  # mapped to GICS industry group "Insurance"
    },
    "TECHNOLOGY": {
        "INFORMATION TECHNOLOGY SERVICES": "^SP500-451020",  # mapped to GICS industry "IT Services"
        "SOFTWARE - INFRASTRUCTURE": "^SP500-451020",  # mapped to GICS industry "IT Services"
        "SOFTWARE - APPLICATION": "^SP500-451030",  # mapped to GICS industry "Software"
        "SYSTEMS SOFTWARE": "^SP500-451030",  # mapped to GICS industry "Software"
        "COMMUNICATION EQUIPMENT": "^SP500-452010",  # mapped to GICS industry "Communications Equipment"
        "CONSUMER ELECTRONICS": "^SP500-4520",  # mapped to GICS industry group "Technology Hardware & Equipment"
        "COMPUTER HARDWARE": "^SP500-4520",  # mapped to GICS industry group "Technology Hardware & Equipment"
        "SCIENTIFIC & TECHNICAL INSTRUMENTS": "^SP500-452030",  # mapped to GICS industry "Electronic Equipment, Instruments & Components"
        "SOLAR": "^SP500-452030",  # mapped to GICS industry "Electronic Equipment, Instruments & Components"
        "ELECTRONIC COMPONENTS": "^SP500-452030",  # mapped to GICS industry "Electronic Equipment, Instruments & Components"
        "ELECTRONIC MANUFACTURING SERVICES": "^SP500-452030",  # mapped to GICS industry "Electronic Equipment, Instruments & Components"
        "ELECTRONICS & COMPUTER DISTRIBUTION": "^SP500-452030",  # mapped to GICS industry "Electronic Equipment, Instruments & Components"
        "SEMICONDUCTOR EQUIPMENT & MATERIALS": "^SP500-453010",  # mapped to GICS industry "Semiconductors & Semiconductor Equipment"
        "SEMICONDUCTORS": "^SP500-453010",  # mapped to GICS industry "Semiconductors & Semiconductor Equipment"
    },
    "COMMUNICATION SERVICES": {
        "ALTERNATIVE CARRIERS": "^SP500-501010",  # mapped to GICS industry "Diversified Telecommunication Services"
        "TELECOM SERVICES": "^SP500-501010",  # mapped to GICS industry "Diversified Telecommunication Services"
        "ADVERTISING AGENCIES": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
        "BROADCASTING": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
        "CABLE & SATELLITE": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
        "PUBLISHING": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
        "ENTERTAINMENT": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
        "ELECTRONIC GAMING & MULTIMEDIA": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
        "INTERNET CONTENT & INFORMATION": "^SP500-5020",  # mapped to GICS industry group "Media & Entertainment"
    },
    "UTILITIES": {
        "UTILITIES - REGULATED ELECTRIC": "^SP500-551010",  # mapped to GICS industry "Electric Utilities"
        "UTILITIES - REGULATED GAS": "^SP500-5510",  # mapped to GICS industry group "Utilities"
        "UTILITIES - DIVERSIFIED": "^SP500-551030",  # mapped to GICS industry "Multi-Utilities"
        "UTILITIES - REGULATED WATER": "^SP500-5510",  # mapped to GICS industry group "Utilities"
        "UTILITIES - INDEPENDENT POWER PRODUCERS": "^SP500-5510",  # mapped to GICS industry group "Utilities"
        "UTILITIES - RENEWABLE": "^SP500-5510",  # mapped to GICS industry group "Utilities"
    },
    "REAL ESTATE": {
        "REIT - DIVERSIFIED": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - INDUSTRIAL": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - HOTEL & MOTEL": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - OFFICE": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - HEALTHCARE FACILITIES": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - RESIDENTIAL": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "SINGLE-FAMILY RESIDENTIAL REITS": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - RETAIL": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "REIT - SPECIALTY": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "SELF-STORAGE REITS": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "TELECOM TOWER REITS": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "TIMBER REITS": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        "DATA CENTER REITS": "^SP500-6010",  # mapped to GICS industry group "Equity Real Estate Investment Trusts (REITs)"
        # "REAL ESTATE - DIVERSIFIED": "^SP500-602010",  # mapped to GICS sub-industry "Diversified Real Estate Activities"
        # "REAL ESTATE OPERATING COMPANIES": "^SP500-602010",
        # "REAL ESTATE - DEVELOPMENT": "^SP500-602010",  # mapped to GICS sub-industry "Real Estate Development"
        # "REAL ESTATE SERVICES": "^SP500-602010",
        "REIT - MORTGAGE": "^SP500-4020",  # mapped to GICS industry group "Financial Services"
    },
}

us_sector_yf_static_tickers_sp400 = {
    "ENERGY": "^SP400-1010",
    "BASIC MATERIALS": "^SP400-15",
    "INDUSTRIALS": "^SP400-20",
    "CONSUMER CYCLICAL": "^SP400-25",
    "CONSUMER DEFENSIVE": "^SP400-30",
    "HEALTHCARE": "^SP400-35",
    "FINANCIAL SERVICES": "^SP400-40",
    "TECHNOLOGY": "^SP400-45",
    "COMMUNICATION SERVICES": "^SP400-50",
    "UTILITIES": "^SP400-55",
    "REAL ESTATE": "^SP400-60",
}

us_industry_yf_static_tickers_sp400 = {
    "ENERGY": {
        "OIL & GAS E&P": "^SP400-10102020",
        "OIL & GAS EQUIPMENT & SERVICES": "^SP400-10101020",
        "OIL & GAS INTEGRATED": "^SP400-10102010",
        "OIL & GAS MIDSTREAM": "^SP400-10102040",  # mapped to GICS sub-industry "Oil & Gas Storage & Transportation"
        "OIL & GAS REFINING & MARKETING": "^SP400-10102030",
        "OIL & GAS DRILLING": "^SP400-10101010",
        "THERMAL COAL": "^SP400-10102050",  # mapped to GICS sub-industry "Coal & Consumable Fuels"
        "URANIUM": "URA",  # No GICS sub-industry for Uranium, so using the Global X Uranium ETF as a proxy
    },
    "BASIC MATERIALS": {
        "COMMODITY CHEMICALS": "^SP400-15101010",
        "CHEMICALS": "^SP400-15101020",  # mapped to GICS sub-industry "Diversified Chemicals"
        "AGRICULTURAL INPUTS": "^SP400-15101030",  # mapped to GICS sub-industry "Fertilizers & Agricultural Chemicals"
        "INDUSTRIAL GASES": "^SP400-15101040",
        "SPECIALTY CHEMICALS": "^SP400-15101050",
        "BUILDING MATERIALS": "^SP400-15102010",  # mapped to GICS sub-industry "Construction Materials"
        "METAL, GLASS & PLASTIC CONTAINERS": "^SP400-15103010",
        "PAPER & PLASTIC PACKAGING PRODUCTS & MATERIALS": "^SP400-15103020",
        "ALUMINUM": "^SP400-15104010",
        "OTHER INDUSTRIAL METALS & MINING": "^SP400-15104020",  # mapped to GICS sub-industry "Diversified Metals & Mining"
        "COPPER": "^SP400-15104025",
        "GOLD": "^SP400-15104030",
        "OTHER PRECIOUS METALS & MINING": "^SP400-15104040",  # mapped to GICS sub-industry "Precious Metals & Minerals"
        "SILVER": "^SP400-15104045",
        "COKING COAL": "^SP400-15104050",  # mapped to GICS sub-industry "Steel"
        "STEEL": "^SP400-15104050",
        "LUMBER & WOOD PRODUCTION": "^SP400-15105010",  # mapped to GICS sub-industry "Forest Products"
        "PAPER & PAPER PRODUCTS": "^SP400-15105020",  # mapped to GICS sub-industry "Paper Products"
    },
    "INDUSTRIALS": {
        "AEROSPACE & DEFENSE": "^SP400-20101010",
        "BUILDING PRODUCTS & EQUIPMENT": "^SP400-20102010",  # mapped to GICS sub-industry "Building Products"
        "ENGINEERING & CONSTRUCTION": "^SP400-20103010",  # mapped to GICS sub-industry "Construction & Engineering"
        "ELECTRICAL EQUIPMENT & PARTS": "^SP400-20104010",  # mapped to GICS sub-industry "Electrical Components & Equipment"
        "HEAVY ELECTRICAL EQUIPMENT": "^SP400-20104020",
        "CONGLOMERATES": "^SP400-20105010",  # mapped to GICS sub-industry "Industrial Conglomerates"
        "CONSTRUCTION MACHINERY & HEAVY TRANSPORTATION EQUIPMENT": "^SP400-20106010",
        "FARM & HEAVY CONSTRUCTION MACHINERY": "^SP400-20106015",  # mapped to GICS sub-industry "Agricultural & Farm Machinery"
        "TOOLS & ACCESSORIES": "^SP400-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "METAL FABRICATION": "^SP400-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "SPECIALTY INDUSTRIAL MACHINERY": "^SP400-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "INDUSTRIAL DISTRIBUTION": "^SP400-20107010",  # mapped to GICS sub-industry "Trading Companies & Distributors"
        "COMMERCIAL PRINTING": "^SP400-20201010",
        "POLLUTION & TREATMENT CONTROLS": "^SP400-20201050",  # mapped to GICS sub-industry "Environmental & Facilities Services"
        "WASTE MANAGEMENT": "^SP400-20201050",  # mapped to GICS sub-industry "Environmental & Facilities Services"
        "OFFICE SERVICES & SUPPLIES": "^SP400-20201060",
        "SPECIALTY BUSINESS SERVICES": "^SP400-20201070",  # mapped to GICS sub-industry "Diversified Support Services"
        "SECURITY & PROTECTION SERVICES": "^SP400-20201080",  # mapped to GICS sub-industry "Security & Alarm Services"
        "STAFFING & EMPLOYMENT SERVICES": "^SP400-20202010",  # mapped to GICS sub-industry "Human Resource & Employment Services"
        "CONSULTING SERVICES": "^SP400-20202020",  # mapped to GICS sub-industry "Research & Consulting Services"
        "DATA PROCESSING & OUTSOURCED SERVICES": "^SP400-20202030",
        "INTEGRATED FREIGHT & LOGISTICS": "^SP400-20301010",  # mapped to GICS sub-industry "Air Freight & Logistics"
        "AIRLINES": "^SP400-20302010",  # mapped to GICS sub-industry "Passenger Airlines"
        "MARINE SHIPPING": "^SP400-20303010",  # mapped to GICS sub-industry "Marine Transportation"
        "RAILROADS": "^SP400-20304010",  # mapped to GICS sub-industry "Rail Transportation"
        "TRUCKING": "^SP400-20304030",  # mapped to GICS sub-industry "Cargo Ground Transportation"
        "PASSENGER GROUND TRANSPORTATION": "^SP400-20304040",
        "AIRPORT SERVICES": "^SP400-20305010",
        "HIGHWAYS & RAILTRACKS": "^SP400-20305020",
        "MARINE PORTS & SERVICES": "^SP400-20305030",
        "RENTAL & LEASING SERVICES": "^SP400-202010",  # no exact GICS sub-industry mapping, map to industry "Commercial Services & Supplies"
    },
    "CONSUMER CYCLICAL": {
        "AUTO PARTS": "^SP400-25101010",  # mapped to GICS sub-industry "Automotive Parts & Equipment"
        "TIRES & RUBBER": "^SP400-25101020",
        "AUTO MANUFACTURERS": "^SP400-25102010",  # mapped to GICS sub-industry "Automobile Manufacturers"
        "MOTORCYCLE MANUFACTURERS": "^SP400-25102010",
        "CONSUMER ELECTRONICS": "^SP400-25201010",
        "FURNISHINGS, FIXTURES & APPLIANCES": "^SP400-25201020",  # mapped to GICS sub-industry "Home Furnishings"
        "RESIDENTIAL CONSTRUCTION": "^SP400-25201030",  # mapped to GICS sub-industry "HOMEBUILDING"
        "HOUSEHOLD APPLIANCES": "^SP400-25201040",
        "HOUSEWARES & SPECIALTIES": "^SP400-25201050",
        "RECREATIONAL VEHICLES": "^SP400-25202010",  # mapped to GICS sub-industry "Leisure Products"
        "LUXURY GOODS": "^SP400-25203010",  # mapped to GICS sub-industry "Apparel, Accessories & Luxury Goods"
        "APPAREL MANUFACTURING": "^SP400-25203010",  # mapped to GICS sub-industry "Apparel, Accessories & Luxury Goods"
        "FOOTWEAR & ACCESSORIES": "^SP400-25203020",  # mapped to GICS sub-industry "Footwear"
        "TEXTILE MANUFACTURING": "^SP400-25203030",  # mapped to GICS sub-industry "Textiles"
        "GAMBLING": "^SP400-25301010",  # mapped to GICS sub-industry "Casinos & Gaming"
        "RESORTS & CASINOS": "^SP400-25301010",  # mapped to GICS sub-industry "Casinos & Gaming"
        "LODGING": "^SP400-25301020",  # mapped to GICS sub-industry "Hotels, Resorts & Cruise Lines"
        "TRAVEL SERVICES": "^SP400-25301020",  # mapped to GICS sub-industry "Hotels, Resorts & Cruise Lines"
        "LEISURE": "^SP400-25301030",  # mapped to GICS sub-industry "Leisure Facilities"
        "RESTAURANTS": "^SP400-25301040",
        "EDUCATION SERVICES": "^SP400-25302010",
        "PERSONAL SERVICES": "^SP400-25302020",  # mapped to GICS sub-industry "Specialized Consumer Services"
        "DISTRIBUTORS": "^SP400-25501010",
        "DEPARTMENT STORES": "^SP400-25503030",  # mapped to GICS sub-industry "Broadline Retail"
        "INTERNET RETAIL": "^SP400-25503030",  # mapped to GICS sub-industry "Broadline Retail"
        "APPAREL RETAIL": "^SP400-25504010",
        "COMPUTER & ELECTRONICS RETAIL": "^SP400-25504020",
        "HOME IMPROVEMENT RETAIL": "^SP400-25504030",
        "SPECIALTY RETAIL": "^SP400-25504040",  # mapped to GICS sub-industry "Other Specialty Retail"
        "AUTO & TRUCK DEALERSHIPS": "^SP400-25504050",  # mapped to GICS sub-industry "Automotive Retail"
        "HOMEFURNISHING RETAIL": "^SP400-25504060",
        "PACKAGING & CONTAINERS": "^SP400-25201050",  # mapped to GICS sub-industry "Housewares & Specialties"
    },
    "CONSUMER DEFENSIVE": {
        "DRUG RETAIL": "^SP400-30101010",
        "FOOD DISTRIBUTION": "^SP400-30101020",  # mapped to GICS sub-industry "Food Distributors"
        "GROCERY STORES": "^SP400-30101030",  # mapped to GICS sub-industry "Food Retail"
        "DISCOUNT STORES": "^SP400-30101040",  # mapped to GICS sub-industry "Consumer Staples Merchandise Retail"
        "BEVERAGES - BREWERS": "^SP400-30201010",  # mapped to GICS sub-industry "Brewers"
        "DISTILLERS & VINTNERS": "^SP400-30201020",
        "BEVERAGES - NON-ALCOHOLIC": "^SP400-30201030",  # mapped to GICS sub-industry "Soft Drinks & Non-alcoholic Beverages"
        "FARM PRODUCTS": "^SP400-30202010",  # mapped to GICS sub-industry "Agricultural Products & Services"
        "CONFECTIONERS": "^SP400-30202030",  # mapped to GICS sub-industry "Packaged Foods & Meats"
        "PACKAGED FOODS": "^SP400-30202030",  # mapped to GICS sub-industry "Packaged Foods & Meats"
        "TOBACCO": "^SP400-30203010",
        "HOUSEHOLD & PERSONAL PRODUCTS": "^SP400-3030",  # mapped to GICS industry-group "Household & Personal Products"
        "EDUCATION & TRAINING SERVICES": "^SP400-25302010",  # mapped to GICS sub-industry "Education Services"
    },
    "HEALTHCARE": {
        "MEDICAL INSTRUMENTS & SUPPLIES": "^SP400-35101010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DEVICES": "^SP400-35101010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DISTRIBUTION": "^SP400-35102010",  # mapped to GICS sub-industry "Health Care Distributors"
        "HEALTH CARE SERVICES": "^SP400-35102015",
        "MEDICAL CARE FACILITIES": "^SP400-35102020",  # mapped to GICS sub-industry "Health Care Facilities"
        "HEALTHCARE PLANS": "^SP400-35102030",  # mapped to GICS sub-industry "Managed Health Care"
        "HEALTH INFORMATION SERVICES": "^SP400-35103010",  # mapped to GICS sub-industry "Health Care Technology"
        "BIOTECHNOLOGY": "^SP400-35201010",
        "DRUG MANUFACTURERS - GENERAL": "^SP400-35202010",  # mapped to GICS sub-industry "Pharmaceuticals"
        "DRUG MANUFACTURERS - SPECIALTY & GENERIC": "^SP400-35202010",  # mapped to GICS sub-industry "Pharmaceuticals"
        "DIAGNOSTICS & RESEARCH": "^SP400-35203010",  # mapped to GICS sub-industry "Life Sciences Tools & Services"
    },
    "FINANCIAL SERVICES": {
        "BANKS - DIVERSIFIED": "^SP400-40101010",  # mapped to GICS sub-industry "Diversified Banks"
        "BANKS - REGIONAL": "^SP400-40101015",  # mapped to GICS sub-industry "Regional Banks"
        "DIVERSIFIED FINANCIAL SERVICES": "^SP400-40201020",
        "FINANCIAL CONGLOMERATES": "^SP400-40201030",  # mapped to GICS sub-industry "Multi-sector Holdings"
        "SPECIALIZED FINANCE": "^SP400-40201040",
        "MORTGAGE FINANCE": "^SP400-40201050",  # mapped to GICS sub-industry "Commercial & Residential Mortgage Finance"
        "TRANSACTION & PAYMENT PROCESSING SERVICES": "^SP400-40201060",
        "CREDIT SERVICES": "^SP400-40202010",  # mapped to GICS sub-industry "Consumer Finance"
        "ASSET MANAGEMENT": "^SP400-40203010",  # mapped to GICS sub-industry "Asset Management & Custody Banks"
        # "INVESTMENT BANKING & BROKERAGE": "^SP400-40203020",
        "CAPITAL MARKETS": "^SP400-40203030",  # mapped to GICS sub-industry "Diversified Capital Markets"
        "FINANCIAL DATA & STOCK EXCHANGES": "^SP400-40203040",  # mapped to GICS sub-industry "Financial Exchanges & Data"
        "MORTGAGE REITS": "^SP400-40204010",
        "INSURANCE BROKERS": "^SP400-40301010",
        "INSURANCE - LIFE": "^SP400-40301020",  # mapped to GICS sub-industry "Life & Health Insurance"
        "INSURANCE - DIVERSIFIED": "^SP400-40301030",  # mapped to GICS sub-industry "Multi-line Insurance"
        "INSURANCE - SPECIALTY": "^SP400-40301040",  # mapped to GICS sub-industry "Property & Casualty Insurance"
        "INSURANCE - PROPERTY & CASUALTY": "^SP400-40301040",  # mapped to GICS sub-industry "Property & Casualty Insurance"
        "INSURANCE - REINSURANCE": "^SP400-40301050",  # mapped to GICS sub-industry "Reinsurance"
    },
    "TECHNOLOGY": {
        "INFORMATION TECHNOLOGY SERVICES": "^SP400-45102010",  # mapped to GICS sub-industry "IT Consulting & Other Services"
        "SOFTWARE - INFRASTRUCTURE": "^SP400-45102030",  # mapped to GICS sub-industry "Internet Services & Infrastructure"
        "SOFTWARE - APPLICATION": "^SP400-45103010",  # mapped to GICS sub-industry "Application Software"
        "SYSTEMS SOFTWARE": "^SP400-45103020",
        "COMMUNICATION EQUIPMENT": "^SP400-45201020",  # mapped to GICS sub-industry "Communications Equipment"
        "CONSUMER ELECTRONICS": "^SP400-45202030",  # mapped to GICS sub-industry "Technology Hardware, Storage & Peripherals"
        "COMPUTER HARDWARE": "^SP400-45202030",  # mapped to GICS sub-industry "Technology Hardware, Storage & Peripherals"
        "SCIENTIFIC & TECHNICAL INSTRUMENTS": "^SP400-45203010",  # mapped to GICS sub-industry "Electronic Equipment & Instruments"
        "SOLAR": "^SP400-45203015",  # mapped to GICS sub-industry "Electronic Components"
        "ELECTRONIC COMPONENTS": "^SP400-45203015",
        "ELECTRONIC MANUFACTURING SERVICES": "^SP400-45203020",
        "ELECTRONICS & COMPUTER DISTRIBUTION": "^SP400-45203030",  # mapped to GICS sub-industry "Technology Distributors"
        "SEMICONDUCTOR EQUIPMENT & MATERIALS": "^SP400-45301010",  # mapped to GICS sub-industry "Semiconductor Materials & Equipment"
        "SEMICONDUCTORS": "^SP400-45301020",
    },
    "COMMUNICATION SERVICES": {
        "ALTERNATIVE CARRIERS": "^SP400-50101010",
        "TELECOM SERVICES": "^SP400-5010",  # mapped to GICS industry group "Telecommunication Services"
        "ADVERTISING AGENCIES": "^SP400-50201010",  # mapped to GICS sub-industry "Advertising"
        "BROADCASTING": "^SP400-50201020",
        "CABLE & SATELLITE": "^SP400-50201030",
        "PUBLISHING": "^SP400-50201040",
        "ENTERTAINMENT": "^SP400-50202010",  # mapped to GICS sub-industry "Movies & Entertainment"
        "ELECTRONIC GAMING & MULTIMEDIA": "^SP400-50202020",  # mapped to GICS sub-industry "Interactive Home Entertainment"
        "INTERNET CONTENT & INFORMATION": "^SP400-50203010",  # mapped to GICS sub-industry "Interactive Media & Services"
    },
    "UTILITIES": {
        "UTILITIES - REGULATED ELECTRIC": "^SP400-55101010",  # mapped to GICS sub-industry "Electric Utilities"
        "UTILITIES - REGULATED GAS": "^SP400-55102010",  # mapped to GICS sub-industry "Gas Utilities"
        "UTILITIES - DIVERSIFIED": "^SP400-55103010",  # mapped to GICS sub-industry "Multi-Utilities"
        "UTILITIES - REGULATED WATER": "^SP400-55104010",  # mapped to GICS sub-industry "Water Utilities"
        "UTILITIES - INDEPENDENT POWER PRODUCERS": "^SP400-55105010",  # mapped to GICS sub-industry "Independent Power Producers & Energy Traders"
        "UTILITIES - RENEWABLE": "^SP400-55105020",  # mapped to GICS sub-industry "Renewable Electricity"
    },
    "REAL ESTATE": {
        "REIT - DIVERSIFIED": "^SP400-60101010",  # mapped to GICS sub-industry "Diversified REITs"
        "REIT - INDUSTRIAL": "^SP400-60102510",  # mapped to GICS sub-industry "Industrial REITs"
        "REIT - HOTEL & MOTEL": "^SP400-60103010",  # mapped to GICS sub-industry "Hotel & Resort REITs"
        "REIT - OFFICE": "^SP400-60104010",  # mapped to GICS sub-industry "Office REITs"
        "REIT - HEALTHCARE FACILITIES": "^SP400-60105010",  # mapped to GICS sub-industry "Health Care REITs"
        "REIT - RESIDENTIAL": "^SP400-60106010",  # mapped to GICS sub-industry "Multi-family Residential REITs"
        "SINGLE-FAMILY RESIDENTIAL REITS": "^SP400-60106020",
        "REIT - RETAIL": "^SP400-60107010",  # mapped to GICS sub-industry "Retail REITs"
        "REIT - SPECIALTY": "^SP400-60108010",  # mapped to GICS sub-industry "Other Specialized REITs"
        "SELF-STORAGE REITS": "^SP400-60108020",
        "TELECOM TOWER REITS": "^SP400-60108030",
        "TIMBER REITS": "^SP400-60108040",
        "DATA CENTER REITS": "^SP400-60108050",
        # "REAL ESTATE - DIVERSIFIED": "^SP400-60201010",  # mapped to GICS sub-industry "Diversified Real Estate Activities"
        # "REAL ESTATE OPERATING COMPANIES": "^SP400-60201020",
        # "REAL ESTATE - DEVELOPMENT": "^SP400-60201030",  # mapped to GICS sub-industry "Real Estate Development"
        # "REAL ESTATE SERVICES": "^SP400-60201040",
        "REIT - MORTGAGE": "^SP400-40204010",  # mapped to GICS sub-industry "Mortgage REITs" under Finance sector!
    },
}

us_sector_yf_static_tickers_sp600 = {
    "ENERGY": "^SP600-1010",
    "BASIC MATERIALS": "^SP600-15",
    "INDUSTRIALS": "^SP600-20",
    "CONSUMER CYCLICAL": "^SP600-25",
    "CONSUMER DEFENSIVE": "^SP600-30",
    "HEALTHCARE": "^SP600-35",
    "FINANCIAL SERVICES": "^SP600-40",
    "TECHNOLOGY": "^SP600-45",
    "COMMUNICATION SERVICES": "^SP600-50",
    "UTILITIES": "^SP600-55",
    "REAL ESTATE": "^SP600-60",
}

us_industry_yf_static_tickers_sp600 = {
    "ENERGY": {
        "OIL & GAS E&P": "^SP600-10102020",
        "OIL & GAS EQUIPMENT & SERVICES": "^SP600-10101020",
        "OIL & GAS INTEGRATED": "^SP600-10102010",
        "OIL & GAS MIDSTREAM": "^SP600-10102040",  # mapped to GICS sub-industry "Oil & Gas Storage & Transportation"
        "OIL & GAS REFINING & MARKETING": "^SP600-10102030",
        "OIL & GAS DRILLING": "^SP600-10101010",
        "THERMAL COAL": "^SP600-10102050",  # mapped to GICS sub-industry "Coal & Consumable Fuels"
        "URANIUM": "URA",  # No GICS sub-industry for Uranium, so using the Global X Uranium ETF as a proxy
    },
    "BASIC MATERIALS": {
        "COMMODITY CHEMICALS": "^SP600-15101010",
        "CHEMICALS": "^SP600-15101020",  # mapped to GICS sub-industry "Diversified Chemicals"
        "AGRICULTURAL INPUTS": "^SP600-15101030",  # mapped to GICS sub-industry "Fertilizers & Agricultural Chemicals"
        "INDUSTRIAL GASES": "^SP600-15101040",
        "SPECIALTY CHEMICALS": "^SP600-15101050",
        "BUILDING MATERIALS": "^SP600-15102010",  # mapped to GICS sub-industry "Construction Materials"
        "METAL, GLASS & PLASTIC CONTAINERS": "^SP600-15103010",
        "PAPER & PLASTIC PACKAGING PRODUCTS & MATERIALS": "^SP600-15103020",
        "ALUMINUM": "^SP600-15104010",
        "OTHER INDUSTRIAL METALS & MINING": "^SP600-15104020",  # mapped to GICS sub-industry "Diversified Metals & Mining"
        "COPPER": "^SP600-15104025",
        "GOLD": "^SP600-15104030",
        "OTHER PRECIOUS METALS & MINING": "^SP600-15104040",  # mapped to GICS sub-industry "Precious Metals & Minerals"
        "SILVER": "^SP600-15104045",
        "COKING COAL": "^SP600-15104050",  # mapped to GICS sub-industry "Steel"
        "STEEL": "^SP600-15104050",
        "LUMBER & WOOD PRODUCTION": "^SP600-15105010",  # mapped to GICS sub-industry "Forest Products"
        "PAPER & PAPER PRODUCTS": "^SP600-15105020",  # mapped to GICS sub-industry "Paper Products"
    },
    "INDUSTRIALS": {
        "AEROSPACE & DEFENSE": "^SP600-20101010",
        "BUILDING PRODUCTS & EQUIPMENT": "^SP600-20102010",  # mapped to GICS sub-industry "Building Products"
        "ENGINEERING & CONSTRUCTION": "^SP600-20103010",  # mapped to GICS sub-industry "Construction & Engineering"
        "ELECTRICAL EQUIPMENT & PARTS": "^SP600-20104010",  # mapped to GICS sub-industry "Electrical Components & Equipment"
        "HEAVY ELECTRICAL EQUIPMENT": "^SP600-20104020",
        "CONGLOMERATES": "^SP600-20105010",  # mapped to GICS sub-industry "Industrial Conglomerates"
        "CONSTRUCTION MACHINERY & HEAVY TRANSPORTATION EQUIPMENT": "^SP600-20106010",
        "FARM & HEAVY CONSTRUCTION MACHINERY": "^SP600-20106015",  # mapped to GICS sub-industry "Agricultural & Farm Machinery"
        "TOOLS & ACCESSORIES": "^SP600-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "METAL FABRICATION": "^SP600-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "SPECIALTY INDUSTRIAL MACHINERY": "^SP600-20106020",  # mapped to GICS sub-industry "Industrial Machinery & Supplies & Components"
        "INDUSTRIAL DISTRIBUTION": "^SP600-20107010",  # mapped to GICS sub-industry "Trading Companies & Distributors"
        "COMMERCIAL PRINTING": "^SP600-20201010",
        "POLLUTION & TREATMENT CONTROLS": "^SP600-20201050",  # mapped to GICS sub-industry "Environmental & Facilities Services"
        "WASTE MANAGEMENT": "^SP600-20201050",  # mapped to GICS sub-industry "Environmental & Facilities Services"
        "OFFICE SERVICES & SUPPLIES": "^SP600-20201060",
        "SPECIALTY BUSINESS SERVICES": "^SP600-20201070",  # mapped to GICS sub-industry "Diversified Support Services"
        "SECURITY & PROTECTION SERVICES": "^SP600-20201080",  # mapped to GICS sub-industry "Security & Alarm Services"
        "STAFFING & EMPLOYMENT SERVICES": "^SP600-20202010",  # mapped to GICS sub-industry "Human Resource & Employment Services"
        "CONSULTING SERVICES": "^SP600-20202020",  # mapped to GICS sub-industry "Research & Consulting Services"
        "DATA PROCESSING & OUTSOURCED SERVICES": "^SP600-20202030",
        "INTEGRATED FREIGHT & LOGISTICS": "^SP600-20301010",  # mapped to GICS sub-industry "Air Freight & Logistics"
        "AIRLINES": "^SP600-20302010",  # mapped to GICS sub-industry "Passenger Airlines"
        "MARINE SHIPPING": "^SP600-20303010",  # mapped to GICS sub-industry "Marine Transportation"
        "RAILROADS": "^SP600-20304010",  # mapped to GICS sub-industry "Rail Transportation"
        "TRUCKING": "^SP600-20304030",  # mapped to GICS sub-industry "Cargo Ground Transportation"
        "PASSENGER GROUND TRANSPORTATION": "^SP600-20304040",
        "AIRPORT SERVICES": "^SP600-20305010",
        "HIGHWAYS & RAILTRACKS": "^SP600-20305020",
        "MARINE PORTS & SERVICES": "^SP600-20305030",
        "RENTAL & LEASING SERVICES": "^SP600-202010",  # no exact GICS sub-industry mapping, map to industry "Commercial Services & Supplies"
    },
    "CONSUMER CYCLICAL": {
        "AUTO PARTS": "^SP600-25101010",  # mapped to GICS sub-industry "Automotive Parts & Equipment"
        "TIRES & RUBBER": "^SP600-25101020",
        "AUTO MANUFACTURERS": "^SP600-25102010",  # mapped to GICS sub-industry "Automobile Manufacturers"
        "MOTORCYCLE MANUFACTURERS": "^SP600-25102010",
        "CONSUMER ELECTRONICS": "^SP600-25201010",
        "FURNISHINGS, FIXTURES & APPLIANCES": "^SP600-25201020",  # mapped to GICS sub-industry "Home Furnishings"
        "RESIDENTIAL CONSTRUCTION": "^SP600-25201030",  # mapped to GICS sub-industry "HOMEBUILDING"
        "HOUSEHOLD APPLIANCES": "^SP600-25201040",
        "HOUSEWARES & SPECIALTIES": "^SP600-25201050",
        "RECREATIONAL VEHICLES": "^SP600-25202010",  # mapped to GICS sub-industry "Leisure Products"
        "LUXURY GOODS": "^SP600-25203010",  # mapped to GICS sub-industry "Apparel, Accessories & Luxury Goods"
        "APPAREL MANUFACTURING": "^SP600-25203010",  # mapped to GICS sub-industry "Apparel, Accessories & Luxury Goods"
        "FOOTWEAR & ACCESSORIES": "^SP600-25203020",  # mapped to GICS sub-industry "Footwear"
        "TEXTILE MANUFACTURING": "^SP600-25203030",  # mapped to GICS sub-industry "Textiles"
        "GAMBLING": "^SP600-25301010",  # mapped to GICS sub-industry "Casinos & Gaming"
        "RESORTS & CASINOS": "^SP600-25301010",  # mapped to GICS sub-industry "Casinos & Gaming"
        "LODGING": "^SP600-25301020",  # mapped to GICS sub-industry "Hotels, Resorts & Cruise Lines"
        "TRAVEL SERVICES": "^SP600-25301020",  # mapped to GICS sub-industry "Hotels, Resorts & Cruise Lines"
        "LEISURE": "^SP600-25301030",  # mapped to GICS sub-industry "Leisure Facilities"
        "RESTAURANTS": "^SP600-25301040",
        "EDUCATION SERVICES": "^SP600-25302010",
        "PERSONAL SERVICES": "^SP600-25302020",  # mapped to GICS sub-industry "Specialized Consumer Services"
        "DISTRIBUTORS": "^SP600-25501010",
        "DEPARTMENT STORES": "^SP600-25503030",  # mapped to GICS sub-industry "Broadline Retail"
        "INTERNET RETAIL": "^SP600-25503030",  # mapped to GICS sub-industry "Broadline Retail"
        "APPAREL RETAIL": "^SP600-25504010",
        "COMPUTER & ELECTRONICS RETAIL": "^SP600-25504020",
        "HOME IMPROVEMENT RETAIL": "^SP600-25504030",
        "SPECIALTY RETAIL": "^SP600-25504040",  # mapped to GICS sub-industry "Other Specialty Retail"
        "AUTO & TRUCK DEALERSHIPS": "^SP600-25504050",  # mapped to GICS sub-industry "Automotive Retail"
        "HOMEFURNISHING RETAIL": "^SP600-25504060",
        "PACKAGING & CONTAINERS": "^SP600-25201050",  # mapped to GICS sub-industry "Housewares & Specialties"
    },
    "CONSUMER DEFENSIVE": {
        "DRUG RETAIL": "^SP600-30101010",
        "FOOD DISTRIBUTION": "^SP600-30101020",  # mapped to GICS sub-industry "Food Distributors"
        "GROCERY STORES": "^SP600-30101030",  # mapped to GICS sub-industry "Food Retail"
        "DISCOUNT STORES": "^SP600-30101040",  # mapped to GICS sub-industry "Consumer Staples Merchandise Retail"
        "BEVERAGES - BREWERS": "^SP600-30201010",  # mapped to GICS sub-industry "Brewers"
        "DISTILLERS & VINTNERS": "^SP600-30201020",
        "BEVERAGES - NON-ALCOHOLIC": "^SP600-30201030",  # mapped to GICS sub-industry "Soft Drinks & Non-alcoholic Beverages"
        "FARM PRODUCTS": "^SP600-30202010",  # mapped to GICS sub-industry "Agricultural Products & Services"
        "CONFECTIONERS": "^SP600-30202030",  # mapped to GICS sub-industry "Packaged Foods & Meats"
        "PACKAGED FOODS": "^SP600-30202030",  # mapped to GICS sub-industry "Packaged Foods & Meats"
        "TOBACCO": "^SP600-30203010",
        "HOUSEHOLD & PERSONAL PRODUCTS": "^SP600-3030",  # mapped to GICS industry-group "Household & Personal Products"
        "EDUCATION & TRAINING SERVICES": "^SP600-25302010",  # mapped to GICS sub-industry "Education Services"
    },
    "HEALTHCARE": {
        "MEDICAL INSTRUMENTS & SUPPLIES": "^SP600-35101010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DEVICES": "^SP600-35101010",  # mapped to GICS industry "Health Care Equipment & Supplies"
        "MEDICAL DISTRIBUTION": "^SP600-35102010",  # mapped to GICS sub-industry "Health Care Distributors"
        "HEALTH CARE SERVICES": "^SP600-35102015",
        "MEDICAL CARE FACILITIES": "^SP600-35102020",  # mapped to GICS sub-industry "Health Care Facilities"
        "HEALTHCARE PLANS": "^SP600-35102030",  # mapped to GICS sub-industry "Managed Health Care"
        "HEALTH INFORMATION SERVICES": "^SP600-35103010",  # mapped to GICS sub-industry "Health Care Technology"
        "BIOTECHNOLOGY": "^SP600-35201010",
        "DRUG MANUFACTURERS - GENERAL": "^SP600-35202010",  # mapped to GICS sub-industry "Pharmaceuticals"
        "DRUG MANUFACTURERS - SPECIALTY & GENERIC": "^SP600-35202010",  # mapped to GICS sub-industry "Pharmaceuticals"
        "DIAGNOSTICS & RESEARCH": "^SP600-35203010",  # mapped to GICS sub-industry "Life Sciences Tools & Services"
    },
    "FINANCIAL SERVICES": {
        "BANKS - DIVERSIFIED": "^SP600-40101010",  # mapped to GICS sub-industry "Diversified Banks"
        "BANKS - REGIONAL": "^SP600-40101015",  # mapped to GICS sub-industry "Regional Banks"
        "DIVERSIFIED FINANCIAL SERVICES": "^SP600-40201020",
        "FINANCIAL CONGLOMERATES": "^SP600-40201030",  # mapped to GICS sub-industry "Multi-sector Holdings"
        "SPECIALIZED FINANCE": "^SP600-40201040",
        "MORTGAGE FINANCE": "^SP600-40201050",  # mapped to GICS sub-industry "Commercial & Residential Mortgage Finance"
        "TRANSACTION & PAYMENT PROCESSING SERVICES": "^SP600-40201060",
        "CREDIT SERVICES": "^SP600-40202010",  # mapped to GICS sub-industry "Consumer Finance"
        "ASSET MANAGEMENT": "^SP600-40203010",  # mapped to GICS sub-industry "Asset Management & Custody Banks"
        # "INVESTMENT BANKING & BROKERAGE": "^SP600-40203020",
        "CAPITAL MARKETS": "^SP600-40203030",  # mapped to GICS sub-industry "Diversified Capital Markets"
        "FINANCIAL DATA & STOCK EXCHANGES": "^SP600-40203040",  # mapped to GICS sub-industry "Financial Exchanges & Data"
        "MORTGAGE REITS": "^SP600-40204010",
        "INSURANCE BROKERS": "^SP600-40301010",
        "INSURANCE - LIFE": "^SP600-40301020",  # mapped to GICS sub-industry "Life & Health Insurance"
        "INSURANCE - DIVERSIFIED": "^SP600-40301030",  # mapped to GICS sub-industry "Multi-line Insurance"
        "INSURANCE - SPECIALTY": "^SP600-40301040",  # mapped to GICS sub-industry "Property & Casualty Insurance"
        "INSURANCE - PROPERTY & CASUALTY": "^SP600-40301040",  # mapped to GICS sub-industry "Property & Casualty Insurance"
        "INSURANCE - REINSURANCE": "^SP600-40301050",  # mapped to GICS sub-industry "Reinsurance"
    },
    "TECHNOLOGY": {
        "INFORMATION TECHNOLOGY SERVICES": "^SP600-45102010",  # mapped to GICS sub-industry "IT Consulting & Other Services"
        "SOFTWARE - INFRASTRUCTURE": "^SP600-45102030",  # mapped to GICS sub-industry "Internet Services & Infrastructure"
        "SOFTWARE - APPLICATION": "^SP600-45103010",  # mapped to GICS sub-industry "Application Software"
        "SYSTEMS SOFTWARE": "^SP600-45103020",
        "COMMUNICATION EQUIPMENT": "^SP600-45201020",  # mapped to GICS sub-industry "Communications Equipment"
        "CONSUMER ELECTRONICS": "^SP600-45202030",  # mapped to GICS sub-industry "Technology Hardware, Storage & Peripherals"
        "COMPUTER HARDWARE": "^SP600-45202030",  # mapped to GICS sub-industry "Technology Hardware, Storage & Peripherals"
        "SCIENTIFIC & TECHNICAL INSTRUMENTS": "^SP600-45203010",  # mapped to GICS sub-industry "Electronic Equipment & Instruments"
        "SOLAR": "^SP600-45203015",  # mapped to GICS sub-industry "Electronic Components"
        "ELECTRONIC COMPONENTS": "^SP600-45203015",
        "ELECTRONIC MANUFACTURING SERVICES": "^SP600-45203020",
        "ELECTRONICS & COMPUTER DISTRIBUTION": "^SP600-45203030",  # mapped to GICS sub-industry "Technology Distributors"
        "SEMICONDUCTOR EQUIPMENT & MATERIALS": "^SP600-45301010",  # mapped to GICS sub-industry "Semiconductor Materials & Equipment"
        "SEMICONDUCTORS": "^SP600-45301020",
    },
    "COMMUNICATION SERVICES": {
        "ALTERNATIVE CARRIERS": "^SP600-50101010",
        "TELECOM SERVICES": "^SP600-5010",  # mapped to GICS industry group "Telecommunication Services"
        "ADVERTISING AGENCIES": "^SP600-50201010",  # mapped to GICS sub-industry "Advertising"
        "BROADCASTING": "^SP600-50201020",
        "CABLE & SATELLITE": "^SP600-50201030",
        "PUBLISHING": "^SP600-50201040",
        "ENTERTAINMENT": "^SP600-50202010",  # mapped to GICS sub-industry "Movies & Entertainment"
        "ELECTRONIC GAMING & MULTIMEDIA": "^SP600-50202020",  # mapped to GICS sub-industry "Interactive Home Entertainment"
        "INTERNET CONTENT & INFORMATION": "^SP600-50203010",  # mapped to GICS sub-industry "Interactive Media & Services"
    },
    "UTILITIES": {
        "UTILITIES - REGULATED ELECTRIC": "^SP600-55101010",  # mapped to GICS sub-industry "Electric Utilities"
        "UTILITIES - REGULATED GAS": "^SP600-55102010",  # mapped to GICS sub-industry "Gas Utilities"
        "UTILITIES - DIVERSIFIED": "^SP600-55103010",  # mapped to GICS sub-industry "Multi-Utilities"
        "UTILITIES - REGULATED WATER": "^SP600-55104010",  # mapped to GICS sub-industry "Water Utilities"
        "UTILITIES - INDEPENDENT POWER PRODUCERS": "^SP600-55105010",  # mapped to GICS sub-industry "Independent Power Producers & Energy Traders"
        "UTILITIES - RENEWABLE": "^SP600-55105020",  # mapped to GICS sub-industry "Renewable Electricity"
    },
    "REAL ESTATE": {
        "REIT - DIVERSIFIED": "^SP600-60101010",  # mapped to GICS sub-industry "Diversified REITs"
        "REIT - INDUSTRIAL": "^SP600-60102510",  # mapped to GICS sub-industry "Industrial REITs"
        "REIT - HOTEL & MOTEL": "^SP600-60103010",  # mapped to GICS sub-industry "Hotel & Resort REITs"
        "REIT - OFFICE": "^SP600-60104010",  # mapped to GICS sub-industry "Office REITs"
        "REIT - HEALTHCARE FACILITIES": "^SP600-60105010",  # mapped to GICS sub-industry "Health Care REITs"
        "REIT - RESIDENTIAL": "^SP600-60106010",  # mapped to GICS sub-industry "Multi-family Residential REITs"
        "SINGLE-FAMILY RESIDENTIAL REITS": "^SP600-60106020",
        "REIT - RETAIL": "^SP600-60107010",  # mapped to GICS sub-industry "Retail REITs"
        "REIT - SPECIALTY": "^SP600-60108010",  # mapped to GICS sub-industry "Other Specialized REITs"
        "SELF-STORAGE REITS": "^SP600-60108020",
        "TELECOM TOWER REITS": "^SP600-60108030",
        "TIMBER REITS": "^SP600-60108040",
        "DATA CENTER REITS": "^SP600-60108050",
        "REAL ESTATE - DIVERSIFIED": "^SP600-60201010",  # mapped to GICS sub-industry "Diversified Real Estate Activities"
        "REAL ESTATE OPERATING COMPANIES": "^SP600-60201020",
        "REAL ESTATE - DEVELOPMENT": "^SP600-60201030",  # mapped to GICS sub-industry "Real Estate Development"
        "REAL ESTATE SERVICES": "^SP600-60201040",
        "REIT - MORTGAGE": "^SP600-40204010",  # mapped to GICS sub-industry "Mortgage REITs" under Finance sector!
    },
}
