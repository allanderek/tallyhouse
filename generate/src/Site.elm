port module Site exposing (main, render)

{-| Renders the Tallyhouse site.

This is a `Platform.worker`: there is no DOM here, only a pure function from
the site data (handed in as JSON flags) to a finished set of files, sent out
through the `emit` port as a single JSON string. Python subscribes to that
port, parses the string, and writes the files — this program never touches
the filesystem itself.

-}

import Data
import Json.Decode as Decode
import Json.Encode as Encode
import Pages exposing (Page)


port emit : String -> Cmd msg


type alias Model =
    ()


type Msg
    = NoOp


main : Program Decode.Value Model Msg
main =
    Platform.worker
        { init = init
        , update = update
        , subscriptions = subscriptions
        }


init : Decode.Value -> ( Model, Cmd Msg )
init flagsValue =
    ( (), emit (render flagsValue) )


{-| The pure heart of the program: flags in, the JSON string to emit out.
Kept separate from `init` so it can be exercised directly in tests, without
a port or a running worker.

A decode failure means the data Python assembled does not match the shape
this program expects — a bug worth failing loudly for. It cannot fail loudly
by crashing the program, though: `--optimize` refuses to build with any use
of `Debug`, and the documented production path uses `--optimize`. Emitting a
JSON error object instead keeps the failure loud (Python's harness treats an
`{"error": ...}` payload as a hard failure carrying this message) while
staying optimisable.

-}
render : Decode.Value -> String
render flagsValue =
    case Decode.decodeValue Data.decodeFlags flagsValue of
        Ok flags ->
            encodePages (Pages.pages flags)

        Err error ->
            encodeError error


update : Msg -> Model -> ( Model, Cmd Msg )
update _ model =
    ( model, Cmd.none )


subscriptions : Model -> Sub Msg
subscriptions _ =
    Sub.none


encodePages : List Page -> String
encodePages listOfPages =
    listOfPages
        |> Encode.list encodePage
        |> Encode.encode 0


encodePage : Page -> Encode.Value
encodePage page =
    Encode.object
        [ ( "path", Encode.string page.path )
        , ( "content", Encode.string page.content )
        ]


encodeError : Decode.Error -> String
encodeError error =
    Encode.encode 0
        (Encode.object [ ( "error", Encode.string (Decode.errorToString error) ) ])
