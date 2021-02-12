use proc_macro::TokenStream;
use quote::quote;
use syn::{parse_macro_input, ItemStruct};

pub fn derive_signal(input: TokenStream) -> TokenStream {
    let input = parse_macro_input!(input as ItemStruct);

    let name = &input.ident;
    let (impl_generics, ty_generics, where_clause) = input.generics.split_for_impl();

    let output = quote! {
        impl #impl_generics Signal for #name #ty_generics #where_clause {
            fn advice(&self) -> crate::Advice {
                self.advice
            }
        }
    };

    TokenStream::from(output)
}
