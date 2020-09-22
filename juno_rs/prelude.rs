// use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, ItemStruct};

pub use crate::time::{
    IntervalIntExt, IntervalStrExt, TimestampStrExt, DAY_MS, HOUR_MS, MIN_MS, MONTH_MS, SEC_MS,
    WEEK_MS, YEAR_MS,
};

#[proc_macro_derive(FieldCount)]
pub fn derive_field_count(input: proc_macro::TokenStream) -> proc_macro::TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let field_count = input.fields.iter().count();

    let name = &input.ident;

    let output = quote! {
        impl #name {
            pub fn field_count() -> usize {
                #field_count
            }
        }
    };

    // Return output tokenstream
    TokenStream::from(output)
}
