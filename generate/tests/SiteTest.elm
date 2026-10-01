module SiteTest exposing (suite)

import Expect
import Json.Decode as Decode
import Json.Encode as Encode
import Site
import Test exposing (Test, describe, test)


{-| `Json.Encode.Value` and `Json.Decode.Value` are the same type, so a value
built here can be handed straight to `Site.render` as if it were the flags
QuickJS would pass in.
-}
wellFormedFlags : Decode.Value
wellFormedFlags =
    Encode.object
        [ ( "index"
          , Encode.object
                [ ( "id", Encode.string "agent-accessibility" )
                , ( "title", Encode.string "Agent Accessibility Index" )
                , ( "question", Encode.string "How many of the top 1000 websites tell AI crawlers to stay out?" )
                ]
          )
        , ( "prints"
          , Encode.list identity
                [ Encode.object
                    [ ( "period", Encode.string "2026-09-14" )
                    , ( "vintage", Encode.string "1" )
                    , ( "value", Encode.string "23.4704" )
                    , ( "denominator", Encode.string "997" )
                    , ( "coverage", Encode.string "99.7" )
                    , ( "provisional", Encode.string "false" )
                    , ( "methodology_version", Encode.string "agents=1;protego=0.6.2" )
                    , ( "collector_version", Encode.string "f5c2b39" )
                    , ( "computed_at", Encode.string "2026-09-17T15:56:22Z" )
                    , ( "reason", Encode.string "" )
                    ]
                ]
          )
        , ( "superseded", Encode.list identity [] )
        , ( "series", Encode.list identity [] )
        , ( "panel"
          , Encode.object
                [ ( "tranco_list_id", Encode.string "N2P2W" )
                , ( "captured", Encode.string "2026-09-17T15:47:47Z" )
                , ( "size", Encode.int 1000 )
                , ( "qualification"
                  , Encode.object
                        [ ( "candidates_examined", Encode.int 1600 )
                        , ( "excluded", Encode.int 556 )
                        , ( "qualified", Encode.int 1000 )
                        , ( "known_bias", Encode.string "sites behind anti-automation challenges are excluded" )
                        , ( "rule", Encode.string "first N domains of the Tranco list" )
                        ]
                  )
                ]
          )
        , ( "agents", Encode.object [] )
        , ( "operators", Encode.object [] )
        , ( "purposes", Encode.object [] )
        , ( "history"
          , Encode.object
                [ ( "id", Encode.string "agent-accessibility-history" )
                , ( "title", Encode.string "Three years of AI-crawler blocking" )
                , ( "question", Encode.string "When did the top websites start telling AI crawlers to stay out?" )
                , ( "prints"
                  , Encode.list identity
                        [ Encode.object
                            [ ( "period", Encode.string "2023-01" )
                            , ( "vintage", Encode.string "1" )
                            , ( "value", Encode.string "1.2821" )
                            , ( "denominator", Encode.string "390" )
                            , ( "coverage", Encode.string "63.8298" )
                            , ( "provisional", Encode.string "false" )
                            , ( "methodology_version", Encode.string "agents=1;protego=0.6.2" )
                            , ( "collector_version", Encode.string "f5c2b39" )
                            , ( "computed_at", Encode.string "2026-09-17T15:56:22Z" )
                            , ( "reason", Encode.string "" )
                            ]
                        ]
                  )
                , ( "superseded", Encode.list identity [] )
                , ( "series", Encode.list identity [] )
                , ( "panel"
                  , Encode.object
                        [ ( "size", Encode.int 611 )
                        , ( "endpoints", Encode.list identity [] )
                        , ( "construction"
                          , Encode.object
                                [ ( "rule", Encode.string "domains present in the Tranco top-N at BOTH endpoints" )
                                , ( "churn", Encode.string "389 of 1000 early entries absent at the later endpoint" )
                                , ( "known_bias", Encode.string "members were prominent at both endpoints" )
                                , ( "not_comparable", Encode.string "a different population from the live index panel" )
                                , ( "retained", Encode.int 611 )
                                ]
                          )
                        ]
                  )
                , ( "crawls", Encode.list identity [] )
                , ( "selection", Encode.string "Roughly quarterly from January 2023 to August 2026." )
                ]
          )
        , ( "crawler"
          , Encode.object
                [ ( "userAgent", Encode.string "TallyhouseIndexBot/1.0 (+https://allanderek.github.io/tallyhouse/about/crawler/)" )
                , ( "token", Encode.string "TallyhouseIndexBot" )
                , ( "category", Encode.string "Academic Research" )
                , ( "purpose", Encode.string "Fetches only /robots.txt, once a week, from a fixed published panel of domains." )
                , ( "contact", Encode.string "https://github.com/allanderek/tallyhouse/issues" )
                , ( "prefixes", Encode.list Encode.string [ "149.102.158.121/32" ] )
                ]
          )
        ]


malformedFlags : Decode.Value
malformedFlags =
    Encode.object [ ( "index", Encode.string "not an object" ) ]


suite : Test
suite =
    describe "Site.render"
        [ test "well-formed flags render a JSON array of pages" <|
            \_ ->
                Site.render wellFormedFlags
                    |> Decode.decodeString (Decode.list (Decode.field "path" Decode.string))
                    |> Expect.equal
                        (Ok
                            [ "index.html"
                            , "agent-accessibility/index.html"
                            , "agent-accessibility-history/index.html"
                            , "agent-accessibility/agents/index.html"
                            , "about/index.html"
                            , "about/crawler/index.html"
                            , "about/crawler/ips.json"
                            ]
                        )
        , test "malformed flags render a JSON error object instead of pages" <|
            \_ ->
                Site.render malformedFlags
                    |> Decode.decodeString (Decode.field "error" Decode.string)
                    |> Result.map (always True)
                    |> Expect.equal (Ok True)
        , test "the error message names what went wrong" <|
            \_ ->
                Site.render malformedFlags
                    |> Decode.decodeString (Decode.field "error" Decode.string)
                    |> Result.withDefault ""
                    |> String.contains "index"
                    |> Expect.equal True
        , test "malformed flags do not decode as a list of pages" <|
            \_ ->
                Site.render malformedFlags
                    |> Decode.decodeString (Decode.list (Decode.field "path" Decode.string))
                    |> Result.toMaybe
                    |> Expect.equal Nothing
        ]
