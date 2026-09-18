port module Site exposing (main)

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


{-| Flags are decoded once, up front. A decode failure here means the data
Python assembled does not match the shape this program expects, which is a
bug worth failing loudly for rather than papering over with a fallback page.
-}
init : Decode.Value -> ( Model, Cmd Msg )
init flagsValue =
    case Decode.decodeValue Data.decodeFlags flagsValue of
        Ok flags ->
            ( (), emit (encodePages (Pages.pages flags)) )

        Err error ->
            Debug.todo (Decode.errorToString error)


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
