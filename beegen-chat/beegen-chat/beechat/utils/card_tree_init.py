"""
Card Tree Initialization Module for BeeChat

This module defines the hierarchical structure of MB Bank card products.
It provides functions to initialize the card hierarchy tree and load it into the database.
"""
import datetime
import json
import logging
from typing import Dict, Any

from beegenerate.storage import MongoStorage
from beegenerate.configs import MongoConfig
from beegenerate.loggings import LOGGER


CARD_HIERARCHY_NEW = {
    "card_types": {
        "credit": {
            "name": "Thẻ tín dụng",
            "keywords": ["tín dụng", "credit", "trả góp", "chi tiêu trước trả tiền sau"],
            "card_ids": ["72", "59", "81", "56", "51", "80", "76"],
            "children": {
                "visa_credit": {
                    "name": "Visa Credit",
                    "keywords": ["visa thẻ tín dụng", "thẻ visa tín dụng", "visa credit card", "tín dụng visa",
                                 "visa td"],
                    "card_ids": ["72", "59", "81"],
                    "children": {
                        "visa_infinite": {
                            "name": "Visa Infinite",
                            "id": "72",
                            "keywords": ["infinite", "visa infinite", "cao cấp", "hạn mức cao", "visa vô hạn"]
                        },
                        "visa_priority": {
                            "name": "Visa Priority",
                            "id": "59",
                            "keywords": ["priority visa", "visa priority", "ưu tiên", "priority td", "visa ưu tiên"]
                        },
                        "visa_credit_vna": {
                            "name": "Visa Credit & VNA",
                            "id": "81",
                            "keywords": ["visa credit tiêu chuẩn", "visa credit thường", "visa credit modern youth",
                                         "visa tín dụng thường",
                                         "vna", "vietnam airlines", "hàng không", "máy bay", "visa vietnam airlines"]
                        }
                    }
                },
                "mastercard_credit": {
                    "name": "Mastercard Credit",
                    "keywords": ["mastercard tín dụng", "master tín dụng", "thẻ master tín dụng", "credit master",
                                 "mastercard td"],
                    "card_ids": ["76"],
                    "children": {
                        "world_elite": {
                            "name": "Priceless World Elite",
                            "id": "76",
                            "keywords": ["world elite", "priceless", "elite", "cao cấp nhất", "thượng hạng",
                                         "mastercard elite"]
                        }
                    }
                },
                "jcb_credit": {
                    "name": "JCB Credit",
                    "keywords": ["jcb tín dụng", "thẻ jcb tín dụng", "jcb credit card", "tín dụng jcb", "jcb td"],
                    "card_ids": ["56", "51", "80"],
                    "children": {
                        "jcb_ultimate": {
                            "name": "JCB Ultimate",
                            "id": "56",
                            "keywords": ["ultimate", "jcb ultimate", "cao cấp", "thượng hạng", "jcb cao cấp"]
                        },
                        "jcb_standard": {
                            "name": "JCB Standard & QR Credit",
                            "id": "51",
                            "keywords": ["jcb credit quốc tế", "jcb credit chuẩn", "jcb credit thường",
                                         "jcb standard credit", "jcb tín dụng thường",
                                         "qr trả sau", "qr credit", "qr tín dụng", "thanh toán qr trả sau"]
                        },
                        "jcb_bamboo": {
                            "name": "JCB Bamboo",
                            "id": "80",
                            "keywords": ["bamboo", "tre", "jcb bamboo", "jcb tre", "thẻ jcb bamboo"]
                        }
                    }
                }
            },
            "special_ids": ["68", "51"]
        },
        "debit": {
            "name": "Thẻ ghi nợ",
            "keywords": ["ghi nợ", "debit", "atm", "thẻ rút tiền"],
            "card_ids": ["66", "67", "65"],
            "children": {
                "domestic": {
                    "name": "Thẻ Ghi nợ Nội địa",
                    "keywords": ["ghi nợ nội địa", "debit nội địa", "trong nước", "thẻ napas", "thẻ ghi nợ nội địa"],
                    "special_ids": ["66"],
                    "children": {
                        "active_plus_combined": {
                            "name": "Active Plus & ViettelPay & VIP/Private & Military",
                            "id": "66",
                            "keywords": ["active plus", "active+", "active debit", "thẻ active", "ghi nợ active",
                                         "viettelpay", "viettel pay", "bankplus", "viettel", "thẻ viettel",
                                         "vip debit", "private debit", "thẻ ghi nợ vip", "thẻ ghi nợ private",
                                         "quân nhân debit", "quân đội debit", "military debit", "thẻ ghi nợ quân đội"]
                        }
                    }
                },
                "international": {
                    "name": "Thẻ ghi nợ Quốc tế",
                    "keywords": ["ghi nợ quốc tế", "debit quốc tế", "international debit", "global debit",
                                 "thẻ ghi nợ quốc tế"],
                    "special_ids": ["51", "68"],
                    "children": {
                        "visa_debit": {
                            "name": "Visa Debit",
                            "id": "67",
                            "keywords": ["visa debit", "visa ghi nợ", "debit visa", "ghi nợ visa", "visa thẻ ghi nợ"]
                        },
                        "unionpay_debit": {
                            "name": "UnionPay Debit",
                            "id": "65",
                            "keywords": ["unionpay", "union pay debit", "ghi nợ trung quốc", "china debit",
                                         "ghi nợ unionpay"]
                        }
                    }
                }
            },
            "special_ids": ["66", "67"]
        },
        "hybrid": {
            "name": "Thẻ đa năng",
            "keywords": ["đa năng", "hybrid", "2in1", "vừa atm vừa tín dụng"],
            "card_ids": ["64", "49", "54", "60", "48", "50", "62", "55", "63"],
            "children": {
                "hi_mastercard": {
                    "name": "Hi Mastercard",
                    "keywords": ["hi mastercard đa năng", "hi master đa năng", "mastercard hybrid", "master hybrid",
                                 "hi master 2in1"],
                    "special_ids":["48","60","54"],
                    "children": {
                        "hi_slaydy_collection": {
                            "name": "Hi Slaydy Collection",
                            "id": "48",
                            "keywords": ["slaydy hybrid", "slay-dy hybrid", "nữ giới", "phái đẹp",
                                         "thẻ nữ giới đa năng",
                                         "hi mastercard", "hi master", "mastercard hi",
                                         "love wins", "tình yêu", "love slaydy", "thẻ love wins",
                                         "make it sweet", "sweet slaydy", "thẻ make it sweet",
                                         "tell me your story", "câu chuyện", "story slaydy", "thẻ tell me your story",
                                         "boss", "sếp", "boss slaydy", "thẻ lãnh đạo",
                                         "game on", "game slaydy", "thẻ game on",
                                         "millionaire", "triệu phú", "millionaire slaydy", "thẻ giàu có",
                                         "awesome", "tuyệt vời", "awesome slaydy", "thẻ amazing",
                                         "my own muse", "nguồn cảm hứng", "muse slaydy", "thẻ inspiration",
                                         "no filter" "no filter slaydy", "thẻ thẳng thắn",
                                         "miracles""miracles slaydy", "thẻ kỳ diệu",
                                         "priority", "ưu tiên", "priority slaydy", "thẻ quan trọng",
                                         "a vibe", "vibe slaydy", "thẻ a vibe"]
                        },
                        "hi_lol_collection": {
                            "name": "Hi LOL Collection",
                            "id": "60",
                            "keywords": ["lol hybrid", "league of legends card", "game hybrid", "hi lol",
                                         "thẻ game thủ",
                                         "ahri", "hồ ly bst", "thẻ ahri",
                                         "ashe", "thẻ ashe",
                                         "blitzcrank", "thẻ blitzcrank",
                                         "cailyn", "thẻ cailyn",
                                         "garen", "thẻ garen",
                                         "kennen", "thẻ kennen",
                                         "lee sin", "thẻ lee sin",
                                         "lucian", "thẻ lucian",
                                         "lulu", "thẻ lulu",
                                         "lux", "ánh sáng bst", "thẻ lux",
                                         "ryze", "phù thủy bst", "thẻ ryze",
                                         "samira", "thẻ samira",
                                         "twisted fate", "thẻ twisted fate",
                                         "wukong", "tôn ngộ không bst", "thẻ wukong",
                                         "xin zhao", "thẻ xin zhao"]
                        },
                        "hi_green_collection": {
                            "name": "Hi Green Collection",
                            "id": "54",
                            "keywords": ["green hybrid", "xanh đa năng", "hi green", "môi trường", "thẻ môi trường",
                                         "green vibes only", "vibes bst", "green vibes card",
                                         "thẻ xanh vibes",
                                         "if not now when", "now bst", "when card", "thẻ khi nào",
                                         "hi green when",
                                         "do something green today", "today bst", "green today card",
                                         "thẻ hành động xanh",
                                         "make green choices", "choices bst", "green choices card",
                                         "thẻ lựa chọn xanh"]
                        }
                    }
                },
                "hi_visa": {
                    "name": "Hi Visa",
                    "keywords": ["hi visa đa năng", "visa hybrid", "visa hi hybrid", "visa 2in1", "hi visa 2in1"],
                    "children": {
                        "hi_visa_collection": {
                            "name": "Hi Visa Collection",
                            "id": "64",
                            "keywords": ["visa hybrid", "hi visa", "bộ sưu tập visa hybrid",
                                         "visa hybrid",
                                         "thẻ tứ quý át", "át", "ace", "bài tây át",
                                         "át rô", "ace of diamonds card", "át chuồn", "thẻ rô",
                                         "át cơ", "ace of hearts card", "át tim", "thẻ cơ",
                                         "át bích", "ace of spades card", "át pic", "thẻ bích",
                                         "át tép", "ace of clubs card", "át nhép", "thẻ tép",
                                         "thẻ tứ quý k", "king", "vua", "bài tây king",
                                         "k rô", "king of diamonds card", "k chuồn", "thẻ k rô",
                                         "k cơ", "king of hearts card", "k tim", "thẻ k cơ",
                                         "k bích", "king of spades card", "k pic", "thẻ k bích",
                                         "k tép", "king of clubs card", "k nhép", "thẻ k tép",
                                         "thẻ tứ quý q", "queen", "hậu", "bài tây queen",
                                         "q rô", "queen of diamonds card", "q chuồn", "thẻ q rô",
                                         "q cơ", "queen of hearts card", "q tim", "thẻ q cơ",
                                         "q bích", "queen of spades card", "q pic", "thẻ q bích",
                                         "q tép", "queen of clubs card", "q nhép", "thẻ q tép",
                                         "thẻ mùa hè", "summer paradise", "summer", "thẻ paradise",
                                         "juicy fruity", "trái cây", "hoa quả",
                                         "thẻ juicy fruity",
                                         "sugar land", "kẹo", "đường", "thẻ sugar land",
                                         "vitamin sea", "sea", "thẻ vitamin sea",
                                         "tropical vibe", "nhiệt đới", "tropical",
                                         "thẻ tropical vibe",
                                         "lucky charm", "bồ đề", "may mắn", "thẻ phong thủy",
                                         "Aries", "Bạch Dương", "cung hoàng đạo", "cung con cừu",
                                         "Taurus", "Kim Ngưu", "cung hoàng đạo con trâu",
                                         "Gemini", "Cung Song Tử",
                                         "Cancer", "Cung Cự giải", "cung con cua",
                                         "Virgo", "Cung xử nữ",
                                         "Leo", "Cung sư tử",
                                         "Libra", "Cung thiên bình",
                                         "Scorpio", "Cung bọ cạp",
                                         "Sagittarius", "Cung Nhân Mã",
                                         "Capricorn", "Cung Ma Kết",
                                         "Quarius", "Cung Bảo Bình",
                                         "Pisces", "Cung song ngư",
                                         "Lady",
                                         "12 con giáp", "Tí", "Sửu", "Dần", "Mão", "Thìn","Tị", "Ngọ", "Mùi", "Thân", "Dậu", "Tuất", "Hợi"
                                         ]
                        },
                        "hi_led_collection": {
                            "name": "Hi LED Collection",
                            "id": "55",
                            "keywords": ["led đa năng", "đèn led hybrid", "hi led hybrid", "thẻ led", "visa phát sáng",
                                         "át rô phát sáng", "lead ace diamond", "đèn led át rô", "át rô led",
                                         "át cơ phát sáng", "lead ace heart", "đèn led át cơ", "át cơ led",
                                         "át bích phát sáng", "lead ace spade", "đèn led át bích", "át bích led",
                                         "át tép phát sáng", "led ace club", "đèn led át tép", "át tép led"]
                        },
                        "stellar_collection": {
                            "name": "Stellar Collection",
                            "id": "63",
                            "keywords": ["stellar hybrid", "vòng đeo tay hybrid", "vòng hybrid", "stellar 2in1",
                                         "vòng tay hybrid", "wearable hybrid", "đeo tay thanh toán",
                                         "vòng thanh toán không tiếp xúc"]
                        }
                    },
                    "special_ids":["55","63","64"],
                },
                "hi_jcb": {
                    "name": "Hi JCB",
                    "keywords": ["hi jcb đa năng", "jcb hybrid", "hi jcb 2in1", "jcb 2in1", "hi jcb hybrid"],
                    "special_ids":["49","62","50"],
                    "children": {
                        "hi_jcb_collection": {
                            "name": "Hi JCB Collection",
                            "id": "49",
                            "keywords": ["collection jcb hybrid", "hi jcb", "bộ sưu tập jcb hybrid", "jcb hybrid",
                                         "maneki neko", "mèo thần tài", "mèo may mắn jcb", "maneki neko jcb",
                                         "mèo áo dài", "áo dài", "mèo áo dài jcb", "thẻ mèo áo dài",
                                         "mèo tứ thân", "tứ thân", "mèo tứ thân jcb", "thẻ mèo tứ thân",
                                         "mèo sức khỏe", "sức khỏe", "mèo health jcb", "thẻ mèo sức khỏe",
                                         "mèo tài lộc", "tài lộc", "mèo fortune jcb", "thẻ mèo tài lộc",
                                         "omamori", "bùa may mắn jcb", "talisman", "omamori jcb",
                                         "omamori may mắn", "may mắn", "omamori luck jcb", "thẻ omamori may mắn",
                                         "omamori tài lộc", "tài lộc", "omamori fortune jcb", "thẻ omamori tài lộc",
                                         "omamori sức khỏe", "sức khỏe", "omamori health jcb", "thẻ omamori sức khỏe",
                                         "omamori thành công", "thành công", "omamori success jcb",
                                         "thẻ omamori thành công",
                                         "japanese culture", "văn hóa nhật", "japan", "thẻ văn hóa nhật",
                                         "origami", "gấp giấy jcb", "nghệ thuật gấp giấy", "thẻ origami",
                                         "sumo", "võ sĩ sumo jcb", "đấu vật nhật", "thẻ sumo",
                                         "sado", "trà đạo jcb", "tea ceremony", "thẻ sado",
                                         "sushi", "ẩm thực nhật jcb", "japanese food", "thẻ sushi"]
                        },
                        "hi_sky_collection": {
                            "name": "Hi Sky Collection",
                            "id": "50",
                            "keywords": ["sky hybrid", "bầu trời đa năng", "hi sky hybrid", "be the sky hybrid",
                                         "skycloud collection", "mây bst", "cloud card", "thẻ skycloud",
                                         "daybreak collection", "bình minh bst", "dawn card", "thẻ daybreak",
                                         "starlight collection", "ánh sao bst", "star card", "thẻ starlight",
                                         "apeiron collection", "vô tận bst", "infinite card", "thẻ apeiron", "Be sky", ]
                        },
                        "hi_shopeefood_collection": {
                            "name": "Hi ShopeeFood Collection",
                            "id": "62",
                            "keywords": ["shopee hybrid", "food hybrid", "đồ ăn đa năng", "hi shopee hybrid",
                                         "shopee food hybrid",
                                         "shopeefood classic", "classic bst", "shopeefood classic jcb",
                                         "thẻ cổ điển shopeefood",
                                         "hà nội ăn gì", "phở bò jcb", "phở", "thẻ phở bò",
                                         "huế ăn chi", "bún bò jcb", "bún bò huế", "thẻ bún bò",
                                         "sài gòn ăn gì", "cơm tấm jcb", "broken rice", "thẻ cơm tấm",
                                         "nha trang ăn gì", "nem nướng jcb", "nem", "thẻ nem nướng",
                                         "hải phòng ăn gì", "bánh đa cua jcb", "bánh đa", "thẻ bánh đa cua",
                                         "đà nẵng ăn gì", "mỳ quảng jcb", "mì quảng", "thẻ mỳ quảng",
                                         "đà nẵng chè", "chè sầu jcb", "chè", "thẻ chè sầu",
                                         "hà nội kem", "kem cốm jcb", "kem", "thẻ kem cốm",
                                         "sài gòn trà sữa", "trà sữa jcb", "bubble tea", "thẻ trà sữa"]
                        }
                    }
                }
            },
            "special_ids": ["64", "49"]
        }
    },
    "brands": {
        "visa": {
            "name": "Visa",
            "keywords": ["visa", "thẻ visa"],
            "card_ids": ["72", "59", "81", "67", "64", "55"],
            "children": {
                "visa_infinite": {
                    "name": "Visa Infinite",
                    "id": "72",
                    "keywords": ["infinite", "visa infinite", "cao cấp", "hạn mức cao"]
                },
                "visa_priority": {
                    "name": "Visa Priority",
                    "id": "59",
                    "keywords": ["priority", "visa priority", "ưu tiên", "priority visa"]
                },
                "visa_credit": {
                    "name": "Visa Credit",
                    "id": "81",
                    "keywords": ["tiêu chuẩn", "quốc tế", "modern youth", "visa credit"]
                },
                "visa_debit": {
                    "name": "Visa Debit",
                    "id": "67",
                    "keywords": ["visa debit", "debit visa", "ghi nợ quốc tế", "visa ghi nợ"]
                },
                "visa_hybrid": {
                    "name": "Visa Hi Collection",
                    "id": "64",
                    "keywords": ["visa hybrid", "visa hi collection", "visa hi", "hi visa collection"]
                }
            },
            "special_ids": ["67", "68", "64"]
        },
        "mastercard": {
            "name": "Mastercard",
            "keywords": ["mastercard", "master", "thẻ master", "master card", "thẻ mastercard"],
            "card_ids": ["76", "48", "54", "60"],
            "children": {
                "world_elite": {
                    "name": "Priceless World Elite",
                    "id": "76",
                    "keywords": ["world elite", "priceless", "elite", "cao cấp nhất", "thượng hạng"]
                },
                "hi_mastercard": {
                    "name": "Hi Mastercard",
                    "ids": ["48", "54", "60"],
                    "keywords": ["hi mastercard", "hi master", "mastercard hi",
                                 "slaydy hybrid", "lol card", "green card"]
                }
            },
            "special_ids": ["76", "48", "54", "60"]
        },
        "jcb": {
            "name": "JCB",
            "keywords": ["jcb", "thẻ jcb", "jcb credit", "credit jcb", "jcb debit", "debit jcb"],
            "card_ids": ["56", "51", "80", "49", "50", "62"],
            "children": {
                "jcb_ultimate": {
                    "name": "JCB Ultimate",
                    "id": "56",
                    "keywords": ["ultimate", "jcb ultimate", "cao cấp", "thượng hạng"]
                },
                "jcb_standard": {
                    "name": "JCB Standard",
                    "id": "51",
                    "keywords": ["jcb quốc tế", "jcb chuẩn", "jcb thường", "jcb standard", "jcb platinum"]
                },
                "jcb_hybrid": {
                    "name": "JCB Hi Collection",
                    "id": "49",
                    "keywords": ["jcb hybrid", "jcb hi collection", "jcb hi", "hi jcb collection"]
                }
            },
            "special_ids": ["51", "49"]
        },
        "unionpay": {
            "name": "UnionPay",
            "keywords": ["unionpay", "union pay", "trung quốc", "china", "unionpay ghi nợ"],
            "card_ids": ["65"],
            "children": {
                "unionpay_debit": {
                    "name": "UnionPay Debit",
                    "id": "65",
                    "keywords": ["unionpay", "union pay", "trung quốc", "china", "unionpay ghi nợ"]
                }
            },
            "special_ids": ["65"]
        }
    }
}
